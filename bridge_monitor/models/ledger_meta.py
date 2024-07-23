from sqlalchemy import Column, DateTime, Boolean, Text
from .meta import Base


class LedgerUpdate(Base):
    __tablename__ = "ledger_meta"

    timestamp = Column(DateTime(timezone=True), nullable=False, primary_key=True)
    failed = Column(Boolean, nullable=False)
    error = Column(Text, nullable=True)
