from sqlalchemy import (
    Column,
    Text,
    Integer,
    ForeignKey,
    DateTime,
)

from .meta import Base


class BlockChain(Base):
    __tablename__ = "block_chain"

    id = Column(Integer, primary_key=True)
    name = Column(Text, nullable=False)
    safe_limit = Column(Integer, nullable=False)


class BlockInfo(Base):
    __tablename__ = "block_info"

    block_chain_id = Column(
        Integer, ForeignKey("block_chain.id"), nullable=False, primary_key=True
    )
    block_number = Column(Integer, primary_key=True, nullable=False)
    timestamp = Column(DateTime(timezone=True), nullable=False)
