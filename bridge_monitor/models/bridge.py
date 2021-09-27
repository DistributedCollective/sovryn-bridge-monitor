from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import (
    Column,
    Integer,
    Text,
    Boolean,
)

from .meta import Base
from .types import Uint256, TZDateTime, now_in_utc


TRANSFER_LATE_DEPOSITED_CUTOFF = timedelta(hours=2)
TRANSFER_LATE_UPDATED_CUTOFF = timedelta(minutes=30)

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

    created_on = Column(TZDateTime, default=now_in_utc, nullable=False)  # TODO: should be seen_on
    updated_on = Column(TZDateTime, default=now_in_utc, nullable=False)

    @property
    def deposited_on(self):
        return datetime.utcfromtimestamp(self.event_block_timestamp).replace(tzinfo=timezone.utc)

    @property
    def executed_on(self):
        if not self.executed_block_timestamp:
            return None
        return datetime.utcfromtimestamp(self.executed_block_timestamp).replace(tzinfo=timezone.utc)

    def is_late(self, now: datetime = None):
        if self.was_processed:
            return False
        if not now:
            now = now_in_utc()
        return (
            now - self.deposited_on > TRANSFER_LATE_DEPOSITED_CUTOFF or
            now - self.updated_on > TRANSFER_LATE_UPDATED_CUTOFF
        )

    @property
    def formatted_amount(self):
        return Decimal(self.amount_wei) / 10**self.token_decimals