from sqlalchemy import Column, DateTime, Boolean, Text
from .meta import Base


class LedgerUpdateMeta(Base):
    __tablename__ = "ledger_update_meta"

    timestamp = Column(DateTime(timezone=True), nullable=False, primary_key=True)
    failed = Column(Boolean, nullable=False)
    error = Column(Text, nullable=True)
