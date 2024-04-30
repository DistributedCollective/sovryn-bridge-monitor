from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import Boolean, Column, Integer, Text
from sqlalchemy.ext.hybrid import hybrid_method, hybrid_property

from .meta import Base
from .types import TZDateTime, Uint256, now_in_utc

TRANSFER_LATE_DEPOSITED_CUTOFF = timedelta(hours=2, minutes=30)
TRANSFER_LATE_UPDATED_CUTOFF = timedelta(minutes=45 + 30)


class Transfer(Base):
    __tablename__ = 'transfer'

    id = Column(Integer, primary_key=True)

    from_chain = Column(Text, nullable=False)
    to_chain = Column(Text, nullable=False)
    transaction_id = Column(Text, nullable=False, index=True)
    transaction_id_old = Column(Text, nullable=False)
    was_processed = Column(Boolean, nullable=False)
    num_votes = Column(Integer, nullable=False)
    receiver_address = Column(Text, nullable=False)
    depositor_address = Column(Text, nullable=False)
    token_address = Column(Text, nullable=False)
    token_symbol = Column(Text, nullable=False)
    token_decimals = Column(Integer, nullable=False)
    amount_wei = Column(Uint256, nullable=False)
    user_data = Column(Text, nullable=False)
    event_block_number = Column(Integer, nullable=False)
    event_block_hash = Column(Text, nullable=False)
    event_block_timestamp = Column(Integer, nullable=False, index=True)
    event_transaction_hash = Column(Text, nullable=False)
    event_log_index = Column(Integer, nullable=False)
    executed_transaction_hash = Column(Text, nullable=True)
    executed_block_hash = Column(Text, nullable=True)
    executed_block_number = Column(Integer, nullable=True)
    executed_block_timestamp = Column(Integer, nullable=True)
    executed_log_index = Column(Integer, nullable=True)
    has_error_token_receiver_events = Column(Boolean, nullable=False)
    error_data = Column(Text, nullable=False)

    ignored = Column(Boolean, nullable=False, default=False)

    created_on = Column(TZDateTime, default=now_in_utc, nullable=False)  # TODO: should be seen_on
    updated_on = Column(TZDateTime, default=now_in_utc, nullable=False)

    @property
    def seen_on(self):
        return self.created_on

    @property
    def deposited_on(self):
        return datetime.utcfromtimestamp(self.event_block_timestamp).replace(tzinfo=timezone.utc)

    @property
    def executed_on(self):
        if not self.executed_block_timestamp:
            return None
        return datetime.utcfromtimestamp(self.executed_block_timestamp).replace(tzinfo=timezone.utc)

    @hybrid_property
    def seconds_from_deposit_to_execution(self):
        if not self.executed_block_timestamp:
            return None
        return self.executed_block_timestamp - self.event_block_timestamp

    @seconds_from_deposit_to_execution.expression
    def seconds_from_deposit_to_execution(self):
        return self.executed_block_timestamp - self.event_block_timestamp

    @hybrid_method
    def is_late(self, now: datetime = None):
        if not now:
            now = now_in_utc()
        return not self.was_processed and (
            now - self.deposited_on > TRANSFER_LATE_DEPOSITED_CUTOFF or
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
        return Decimal(self.amount_wei) / 10**self.token_decimals

    @property
    def vote_command(self):
        deposit_chain = 'rsk' if self.from_chain.startswith('rsk_') else 'other'
        env_vars = ''
        if self.bridge_name.startswith('rsk_eth'):
            env_vars = 'INFURA_API_KEY=keygoeshere '
        return (
            f"{env_vars}venv/bin/python vote_bridge_tx.py --bridge {self.bridge_name} --deposit-chain {deposit_chain} "
            f"--tx-hash {self.event_transaction_hash}"
        )

    @property
    def bridge_name(self):
        chains = {self.from_chain, self.to_chain}
        if chains == {'rsk_mainnet', 'eth_mainnet'}:
            return 'rsk_eth_mainnet'
        if chains == {'rsk_mainnet', 'bsc_mainnet'}:
            return 'rsk_bsc_mainnet'
        if chains == {'rsk_testnet', 'eth_testnet_ropsten'}:
            return 'rsk_eth_testnet'
        if chains == {'rsk_testnet', 'bsc_testnet'}:
            return 'rsk_bsc_testnet'
        return 'unknown'
