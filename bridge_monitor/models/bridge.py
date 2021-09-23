from sqlalchemy import (
    Column,
    Integer,
    Text,
    Boolean,
)

from .meta import Base


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
    token_address = Column(Text, nullable=False)
    token_symbol = Column(Text, nullable=False)
    amount_wei = Column(Integer, nullable=False)
    user_data = Column(Text, nullable=False)
    event_block_number = Column(Integer, nullable=False)
    event_block_hash = Column(Text, nullable=False)
    event_transaction_hash = Column(Text, nullable=False)
    event_log_index = Column(Integer, nullable=False)
    executed_transaction_hash = Column(Text, nullable=False)
    executed_block_hash = Column(Text, nullable=False)
    executed_block_number = Column(Integer, nullable=False)
    executed_log_index = Column(Integer, nullable=False)
    has_error_token_receiver_events = Column(Boolean, nullable=False)
    error_data = Column(Text, nullable=False)