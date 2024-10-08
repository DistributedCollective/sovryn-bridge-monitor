import enum
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Union

from eth_utils import to_hex
from sqlalchemy import Boolean, Column, Index, Integer, Text, Enum
from sqlalchemy.ext.hybrid import hybrid_method, hybrid_property
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm.session import Session
from sqlalchemy.orm.attributes import flag_modified

from .meta import Base
from .types import TZDateTime, Uint256, now_in_utc
from .pnl import HasPnL

FASTBTC_IN_TRANSFER_LATE_DEPOSITED_CUTOFF = timedelta(hours=2, minutes=30)
FASTBTC_IN_TRANSFER_LATE_UPDATED_CUTOFF = timedelta(minutes=45 + 30)

WEI_IN_RBTC = 10**18


class FastBTCInTransferStatus(enum.IntEnum):
    INITIATED = 0
    SUBMITTED = 1
    PARTIALLY_CONFIRMED = 2
    EXECUTED = 3
    INVALID = 255


class FastBTCInTransfer(HasPnL, Base):
    __tablename__ = "fastbtc_in_transfer"
    id = Column(Integer, primary_key=True)

    chain = Column(Text, nullable=False)
    multisig_tx_id = Column(Uint256, nullable=False)
    rsk_receiver_address = Column(Text, nullable=False)
    bitcoin_tx_hash = Column(Text, nullable=True)
    bitcoin_tx_vout = Column(Integer, nullable=True)
    transfer_function = Column(
        Text, nullable=False, default=""
    )  # e.g. transferToUser/withdrawAdmin/etc

    net_amount_wei = Column(Uint256, nullable=False)
    fee_wei = Column(Uint256, nullable=True)

    status = Column(
        Enum(FastBTCInTransferStatus, name="fastbtc_in_transferstatus"),
        nullable=False,
        default=FastBTCInTransferStatus.INITIATED,
    )
    num_confirmations = Column(Integer, nullable=False, default=0)
    has_execution_failure = Column(Boolean, nullable=True, default=False)

    ignored = Column(Boolean, nullable=False, default=False)

    submission_block_number = Column(Integer, nullable=True)
    submission_block_hash = Column(Text, nullable=True)
    submission_block_timestamp = Column(Integer, nullable=True, index=True)
    submission_transaction_hash = Column(Text, nullable=True)
    submission_log_index = Column(Integer, nullable=True)

    executed_block_number = Column(Integer, nullable=True)
    executed_block_hash = Column(Text, nullable=True)
    executed_block_timestamp = Column(Integer, nullable=True, index=True)
    executed_transaction_hash = Column(Text, nullable=True)
    executed_log_index = Column(Integer, nullable=True)

    seen_on = Column(TZDateTime, default=now_in_utc, nullable=False)
    updated_on = Column(TZDateTime, default=now_in_utc, nullable=False)

    extra_data = Column(JSONB, default=dict, server_default="{}", nullable=False)

    is_double_spend = Column(
        Boolean, nullable=False, default=False, server_default="false"
    )

    __table_args__ = (Index("ix_fastbtc_in_chain_tx_id", "chain", "multisig_tx_id"),)

    @classmethod
    def get_or_create(
        cls,
        dbsession: Session,
        *,
        chain: str,
        multisig_tx_id: int,
        rsk_receiver_address: str,
        bitcoin_tx_hash: str = None,
        bitcoin_tx_vout: int = None,
        transfer_function: str = "",
        net_amount_wei: int,
        fee_wei: int = None,
    ):
        ret = (
            dbsession.query(cls)
            .filter_by(
                chain=chain,
                multisig_tx_id=multisig_tx_id,
            )
            .one_or_none()
        )
        if ret:
            return ret
        ret = cls(
            chain=chain,
            multisig_tx_id=multisig_tx_id,
            rsk_receiver_address=rsk_receiver_address,
            bitcoin_tx_hash=bitcoin_tx_hash,
            bitcoin_tx_vout=bitcoin_tx_vout,
            transfer_function=transfer_function,
            net_amount_wei=net_amount_wei,
            fee_wei=fee_wei,
        )
        dbsession.add(ret)
        dbsession.flush()
        return ret

    @property
    def created_on(self):
        # Backwards compat
        return self.seen_on

    @property
    def submitted_on(self):
        if not self.submission_block_timestamp:
            return None
        return datetime.utcfromtimestamp(self.submission_block_timestamp).replace(
            tzinfo=timezone.utc
        )

    @property
    def executed_on(self):
        if not self.executed_block_timestamp:
            return None
        return datetime.utcfromtimestamp(self.executed_block_timestamp).replace(
            tzinfo=timezone.utc
        )

    @hybrid_property
    def was_processed(self):
        return self.status == FastBTCInTransferStatus.EXECUTED

    @hybrid_method
    def is_late(self, now: datetime = None):
        if not now:
            now = now_in_utc()
        return not self.was_processed and (
            now - self.submitted_on > FASTBTC_IN_TRANSFER_LATE_DEPOSITED_CUTOFF
            or now - self.updated_on > FASTBTC_IN_TRANSFER_LATE_UPDATED_CUTOFF
        )

    @is_late.expression
    def is_late(self, now: datetime = None):
        if not now:
            now = now_in_utc()
        now_ts = int(now.timestamp())
        return ~self.was_processed & (
            (
                now_ts - self.submission_block_timestamp
                > FASTBTC_IN_TRANSFER_LATE_DEPOSITED_CUTOFF.total_seconds()
            )
            | (now - self.updated_on > FASTBTC_IN_TRANSFER_LATE_UPDATED_CUTOFF)
        )

    @property
    def formatted_fee(self):
        return Decimal(self.fee_wei) / WEI_IN_RBTC

    @property
    def formatted_net_amount(self):
        return Decimal(self.net_amount_wei) / WEI_IN_RBTC

    @property
    def confirmations(self):
        return self.extra_data.get("confirmations", [])

    @property
    def revocations(self):
        return self.extra_data.get("revocations", [])

    @property
    def execution_failures(self):
        return self.extra_data.get('execution_failures', [])

    def update_status(self, new_status: FastBTCInTransferStatus):
        # Only update upwards, except for INVALID
        if (
            new_status == FastBTCInTransferStatus.INVALID
            or self.status == FastBTCInTransferStatus.INVALID
            or new_status > self.status
        ):
            self.status = new_status
            self.updated_on = now_in_utc()

    def mark_submitted(
        self,
        *,
        tx_hash: Union[str, bytes],
        timestamp: int,
        block_number: int,
        block_hash: Union[str, bytes],
        log_index: int,
    ):
        self.update_status(FastBTCInTransferStatus.SUBMITTED)
        self.submission_transaction_hash = to_hex_if_bytes(tx_hash)
        self.submission_block_timestamp = timestamp
        self.submission_block_number = block_number
        self.submission_block_hash = to_hex_if_bytes(block_hash)
        self.submission_log_index = log_index

    def add_confirmation(self, *, sender: str, tx_hash: Union[bytes, str]):
        if "confirmations" not in self.extra_data:
            self.extra_data["confirmations"] = []

        flag_modified(
            self, "extra_data"
        )  # have to flag it as modified for sqlalchemy to save

        for confirmation in self.extra_data["confirmations"]:
            if confirmation["sender"].lower() == sender.lower():
                confirmation["tx_hash"] = to_hex_if_bytes(tx_hash)
                return

        self.extra_data["confirmations"].append(
            {
                "sender": sender,
                "tx_hash": to_hex_if_bytes(tx_hash),
            }
        )
        self.update_status(FastBTCInTransferStatus.PARTIALLY_CONFIRMED)
        self.num_confirmations = len(self.extra_data["confirmations"])
        self.updated_on = now_in_utc()

    def revoke_confirmation(self, *, sender: str, tx_hash: Union[bytes, str]):
        if "confirmations" not in self.extra_data:
            self.extra_data["confirmations"] = []
        if "revocations" not in self.extra_data:
            self.extra_data["revocations"] = []

        flag_modified(
            self, "extra_data"
        )  # have to flag it as modified for sqlalchemy to save

        new_confirmations = []
        revoked_confirmation_tx_hash = None
        for confirmation in self.extra_data["confirmations"]:
            if confirmation["sender"].lower() == sender.lower():
                revoked_confirmation_tx_hash = confirmation["tx_hash"]
            else:
                new_confirmations.append(confirmation)

        if revoked_confirmation_tx_hash is not None:
            # Previously confirmed by sender, update confirmations
            self.extra_data["confirmations"] = new_confirmations
            self.num_confirmations = len(self.extra_data["confirmations"])

            self.extra_data["revocations"].append(
                {
                    "sender": sender,
                    "tx_hash": to_hex_if_bytes(tx_hash),
                    "revoked_confirmation_tx_hash": revoked_confirmation_tx_hash,
                }
            )
        self.updated_on = now_in_utc()

    def mark_executed(
        self,
        *,
        tx_hash: Union[str, bytes],
        timestamp: int,
        block_number: int,
        block_hash: Union[str, bytes],
        log_index: int,
    ):
        self.update_status(FastBTCInTransferStatus.EXECUTED)
        self.executed_transaction_hash = to_hex_if_bytes(tx_hash)
        self.executed_block_timestamp = timestamp
        self.executed_block_number = block_number
        self.executed_block_hash = to_hex_if_bytes(block_hash)
        self.executed_log_index = log_index

    def mark_execution_failed(
        self,
        *,
        tx_hash: Union[str, bytes]
    ):
        self.has_execution_failure = True
        if 'execution_failures' not in self.extra_data:
            self.extra_data['execution_failures'] = []

        flag_modified(
            self, "extra_data"
        )  # have to flag it as modified for sqlalchemy to save

        self.extra_data["execution_failures"].append(
            {
                "tx_hash": to_hex_if_bytes(tx_hash),
            }
        )


def to_hex_if_bytes(val: Union[str, bytes]) -> str:
    if isinstance(val, bytes):
        return to_hex(val)
    return val
