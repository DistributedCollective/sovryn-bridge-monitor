from sqlalchemy import (
    Column,
    Text,
    Integer,
    ForeignKey,
    UniqueConstraint,
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
    Numeric,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from .chain_info import BlockInfo
from .meta import Base


class RskAddress(Base):
    __tablename__ = "rsk_address"
    __table_args__ = (
        CheckConstraint("LOWER(address) = address", name="address_lowercase"),
    )
    address_id = Column(Integer, primary_key=True)
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
        "RskTransactionInfoOld",
        cascade="all, delete-orphan",
        back_populates="address",
        lazy="dynamic",
        single_parent=True,
    )


class RskAddressBookkeeper(Base):
    __tablename__ = "rsk_tx_bookkeeper"

    address_id = Column(Integer, ForeignKey("rsk_address.address_id"), primary_key=True)
    address = relationship(RskAddress, back_populates="bookkeeper")
    start = Column(Integer, nullable=False, default=1)
    end = Column(Integer, nullable=True)
    lowest_scanned = Column(Integer, nullable=False)
    next_to_scan_high = Column(Integer, nullable=False)


class RskTransactionInfoOld(Base):
    __tablename__ = "rsk_tx_info_old"
    __table_args__ = (
        UniqueConstraint("address_id", "tx_hash"),
        ForeignKeyConstraint(
            ["block_number", "chain_id"],
            ["block_info.block_number", "block_info.block_chain_id"],
        ),
    )

    id = Column(Integer, primary_key=True)
    address_id = Column(Integer, ForeignKey("rsk_address.address_id"), nullable=False)
    tx_hash = Column(Text, nullable=False)
    block_number = Column(Integer, nullable=True)
    chain_id = Column(Integer, nullable=True)
    blocktime = Column(DateTime(timezone=True), nullable=True)
    trace_json = Column(JSONB, nullable=False)
    address = relationship(RskAddress, back_populates="transactions")
    block_info = relationship(
        BlockInfo,
        primaryjoin="and_(RskTransactionInfoOld.block_number == BlockInfo.block_number,"
        "RskTransactionInfoOld.chain_id == BlockInfo.block_chain_id)",
    )


class RskTxTrace(Base):
    __tablename__ = "rsk_tx_trace"
    __table_args__ = (
        UniqueConstraint("tx_hash", "trace_index"),
        ForeignKeyConstraint(
            ["block_number", "chain_id"],
            ["block_info.block_number", "block_info.block_chain_id"],
        ),
        CheckConstraint("LOWER(to_address) = to_address", name="to_address_lowercase"),
        CheckConstraint(
            "LOWER(from_address) = from_address", name="from_address_lowercase"
        ),
    )

    id = Column(Integer, primary_key=True)
    tx_hash = Column(Text, nullable=False)
    block_number = Column(Integer, nullable=True)
    chain_id = Column(Integer, nullable=True)
    block_time = Column(DateTime(timezone=True), nullable=True)
    to_address = Column(Text, nullable=False)
    from_address = Column(Text, nullable=False)
    trace_index = Column(Integer, nullable=False)
    value = Column(Numeric(42, 18), nullable=False)
    unmapped = Column(JSONB, nullable=False)
    error = Column(Text)
    block_info = relationship(
        BlockInfo,
        primaryjoin="and_(RskTxTrace.block_number == BlockInfo.block_number,"
        "RskTxTrace.chain_id == BlockInfo.block_chain_id)",
    )
