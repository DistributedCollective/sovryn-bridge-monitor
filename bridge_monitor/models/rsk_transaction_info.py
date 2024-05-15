from sqlalchemy import (
    Column,
    Text,
    Integer,
    ForeignKey,
    UniqueConstraint,
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from .chain_info import BlockInfo
from .meta import Base


class RskAddress(Base):
    __tablename__ = "rsk_address"
    __table_args__ = (
        CheckConstraint("LOWER(address) = address", name="lowercase_address"),
    )
    id = Column(Integer, primary_key=True)
    address = Column(Text, nullable=False, unique=True)
    name = Column(Text, nullable=True)
    bookkeeper = relationship(
        "RskAddressBookkeeper",
        back_populates="address",
        cascade="all, delete-orphan",
        single_parent=True,
        uselist=False,
    )
    transactions = relationship(
        "RskTransactionInfo",
        cascade="all, delete-orphan",
        back_populates="address",
        lazy="dynamic",
        single_parent=True,
    )


class RskAddressBookkeeper(Base):
    __tablename__ = "rsk_tx_bookkeeper"

    address_id = Column(Integer, ForeignKey("rsk_address.id"), primary_key=True)
    address = relationship(RskAddress, back_populates="bookkeeper")
    start = Column(Integer, nullable=False, default=1)
    end = Column(Integer, nullable=True)
    lowest_scanned = Column(Integer, nullable=False)
    next_to_scan_high = Column(Integer, nullable=False)


class RskTransactionInfo(Base):
    __tablename__ = "rsk_tx_info"
    __table_args__ = (
        UniqueConstraint("address_id", "tx_hash", name="unique_tx"),
        ForeignKeyConstraint(
            ["block_n", "chain_id"],
            ["block_info.block_number", "block_info.block_chain_id"],
            name="fk_block_info",
        ),
    )

    id = Column(Integer, primary_key=True)
    address_id = Column(Integer, ForeignKey("rsk_address.id"), nullable=False)
    tx_hash = Column(Text, nullable=False)
    block_n = Column(Integer, nullable=True)
    chain_id = Column(Integer, nullable=True)
    blocktime = Column(DateTime(timezone=True), nullable=True)
    trace_json = Column(JSONB, nullable=False)
    address = relationship(RskAddress, back_populates="transactions")
    block_info = relationship(
        BlockInfo,
        primaryjoin="and_(RskTransactionInfo.block_n == BlockInfo.block_number,"
        "RskTransactionInfo.chain_id == BlockInfo.block_chain_id)",
    )
