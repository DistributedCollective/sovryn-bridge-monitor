from sqlalchemy import (
    Column,
    Text,
    Integer,
    ForeignKey,
    UniqueConstraint, CheckConstraint
)

from .meta import Base
from sqlalchemy.orm import relationship

class RskAddress(Base):
    __tablename__ = "rsk_address"
    __table_args__ = (
        CheckConstraint("LOWER(address) = address", name="lowercase_address"),
    )
    id = Column(Integer, primary_key=True)
    address = Column(Text, nullable=False, unique=True)
    name = Column(Text, nullable=True)
    bookkeeper = relationship("RskAddressBookkeeper", back_populates="address", cascade="all, delete-orphan",
                              single_parent=True, uselist=False)
    transactions = relationship("RskTransactionInfo", cascade="all, delete-orphan",
                                back_populates="address", lazy="dynamic", single_parent=True)

class RskAddressBookkeeper(Base):
    __tablename__ = 'rsk_tx_bookkeeper'

    address_id = Column(Integer, ForeignKey("rsk_address.id"), primary_key=True)
    address = relationship(RskAddress, back_populates="bookkeeper")
    start = Column(Integer, nullable=False, default=1)
    end = Column(Integer, nullable=True)
    lowest_scanned = Column(Integer, nullable=False)
    next_to_scan_high = Column(Integer, nullable=False)


class RskTransactionInfo(Base):
    __tablename__ = 'rsk_tx_info'
    __table_args__ = (
        UniqueConstraint("address_id", "tx_hash", name="unique_tx"),
    )
    id = Column(Integer, primary_key=True)
    address_id = Column(Integer, ForeignKey("rsk_address.id"), nullable=False)
    address = relationship(RskAddress, back_populates="transactions")
    tx_hash = Column(Text, nullable=False)
    block_n = Column(Integer, nullable=False)
