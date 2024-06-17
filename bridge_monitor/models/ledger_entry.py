from sqlalchemy import (
    Column,
    Text,
    Integer,
    ForeignKey,
    DateTime,
    Boolean,
    Numeric,
)

from sqlalchemy.orm import relationship

from .meta import Base


class LedgerAccount(Base):
    __tablename__ = "ledger_account"

    id = Column(Integer, primary_key=True)
    name = Column(Text, nullable=False, unique=True)
    is_debit = Column(Boolean, nullable=False)
    entries = relationship("LedgerEntry", back_populates="account", lazy="dynamic")


class LedgerEntry(Base):
    __tablename__ = "ledger_entry"

    id = Column(Integer, primary_key=True)
    tx_hash = Column(Text, nullable=False)
    timestamp = Column(DateTime(timezone=True), nullable=False)
    account_id = Column(Integer, ForeignKey(LedgerAccount.id), nullable=False)
    value = Column(Numeric(40, 18), nullable=False)
    vout = Column(Integer, nullable=True)
    account = relationship("LedgerAccount", back_populates="entries")
