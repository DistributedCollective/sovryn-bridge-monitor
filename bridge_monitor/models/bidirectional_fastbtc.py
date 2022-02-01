import enum
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import Boolean, Column, Index, Integer, Text, Enum
from sqlalchemy.ext.hybrid import hybrid_method, hybrid_property

from .meta import Base
from .types import TZDateTime, Uint256, now_in_utc

TRANSFER_LATE_DEPOSITED_CUTOFF = timedelta(hours=2)
TRANSFER_LATE_UPDATED_CUTOFF = timedelta(minutes=45)
WEI_IN_SATOSHI = 10_000_000_000
SATOSHI_IN_BTC = 100_000_000


class TransferStatus(enum.IntEnum):
    NOT_APPLICABLE = 0
    NEW = 1
    SENDING = 2
    MINED = 3
    REFUNDED = 4
    RECLAIMED = 5
    INVALID = 255


class BidirectionalFastBTCTransfer(Base):
    __tablename__ = 'bidi_fastbtc_transfer'
    id = Column(Integer, primary_key=True)

    chain = Column(Text, nullable=False)
    transfer_id = Column(Text, nullable=False)
    rsk_address = Column(Text, nullable=False)
    bitcoin_address = Column(Text, nullable=False)
    total_amount_satoshi = Column(Uint256, nullable=False)
    net_amount_satoshi = Column(Uint256, nullable=False)
    fee_satoshi = Column(Uint256, nullable=False)
    status = Column(Enum(TransferStatus, name='bidi_fastbtc_transferstatus'), nullable=False)
    bitcoin_tx_id = Column(Text, nullable=True)

    ignored = Column(Boolean, nullable=False, default=False)

    event_block_number = Column(Integer, nullable=False)
    event_block_hash = Column(Text, nullable=False)
    event_block_timestamp = Column(Integer, nullable=False, index=True)
    event_transaction_hash = Column(Text, nullable=False)
    event_log_index = Column(Integer, nullable=False)

    transfer_batch_size = Column(Integer, nullable=True)
    marked_as_sending_transaction_hash = Column(Text, nullable=True)
    marked_as_sending_block_hash = Column(Text, nullable=True)
    marked_as_sending_block_number = Column(Integer, nullable=True)
    marked_as_sending_block_timestamp = Column(Integer, nullable=True)
    marked_as_sending_log_index = Column(Integer, nullable=True)

    marked_as_mined_transaction_hash = Column(Text, nullable=True)
    marked_as_mined_block_hash = Column(Text, nullable=True)
    marked_as_mined_block_number = Column(Integer, nullable=True)
    marked_as_mined_block_timestamp = Column(Integer, nullable=True)
    marked_as_mined_log_index = Column(Integer, nullable=True)

    refunded_or_reclaimed_transaction_hash = Column(Text, nullable=True)
    refunded_or_reclaimed_block_hash = Column(Text, nullable=True)
    refunded_or_reclaimed_block_number = Column(Integer, nullable=True)
    refunded_or_reclaimed_block_timestamp = Column(Integer, nullable=True)
    refunded_or_reclaimed_log_index = Column(Integer, nullable=True)

    seen_on = Column(TZDateTime, default=now_in_utc, nullable=False)
    updated_on = Column(TZDateTime, default=now_in_utc, nullable=False)

    __table_args__ = (
        Index('ix_chain_transfer_id', 'chain', 'transfer_id'),
    )

    @property
    def created_on(self):
        # Backwards compat
        return self.seen_on

    @property
    def initiated_on(self):
        return datetime.utcfromtimestamp(self.event_block_timestamp).replace(tzinfo=timezone.utc)

    @property
    def marked_as_sending_on(self):
        if not self.marked_as_sending_block_timestamp:
            return None
        return datetime.utcfromtimestamp(self.marked_as_sending_block_timestamp).replace(tzinfo=timezone.utc)

    @property
    def marked_as_mined_on(self):
        if not self.marked_as_mined_block_timestamp:
            return None
        return datetime.utcfromtimestamp(self.marked_as_mined_block_timestamp).replace(tzinfo=timezone.utc)

    @property
    def refunded_or_reclaimed_on(self):
        if not self.refunded_or_reclaimed_block_timestamp:
            return None
        return datetime.utcfromtimestamp(self.refunded_or_reclaimed_block_timestamp).replace(tzinfo=timezone.utc)

    @hybrid_property
    def was_processed(self):
        return self.status in (TransferStatus.MINED, TransferStatus.REFUNDED, TransferStatus.RECLAIMED)

    @was_processed.expression
    def was_processed(self):
        return self.status.in_([TransferStatus.MINED, TransferStatus.REFUNDED, TransferStatus.RECLAIMED])

    @hybrid_method
    def is_late(self, now: datetime = None):
        if not now:
            now = now_in_utc()
        return not self.was_processed and (
            now - self.initiated_on > TRANSFER_LATE_DEPOSITED_CUTOFF or
            now - self.updated_on > TRANSFER_LATE_UPDATED_CUTOFF
        )

    @is_late.expression
    def is_late(self, now: datetime = None):
        if not now:
            now = now_in_utc()
        now_ts = int(now.timestamp())
        return ~self.was_processed & (
            (now_ts - self.event_block_timestamp > TRANSFER_LATE_DEPOSITED_CUTOFF.total_seconds()) |
            (now - self.updated_on > TRANSFER_LATE_UPDATED_CUTOFF)
        )

    @property
    def formatted_amount(self):
        return Decimal(self.total_amount_satoshi) / SATOSHI_IN_BTC

    @property
    def formatted_fee(self):
        return Decimal(self.fee_satoshi) / SATOSHI_IN_BTC

    @property
    def formatted_net_amount(self):
        return Decimal(self.net_amount_satoshi) / SATOSHI_IN_BTC
