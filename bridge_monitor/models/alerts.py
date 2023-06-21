import enum

from sqlalchemy import Boolean, Column, Enum, Integer

from .meta import Base
from .types import TZDateTime, now_in_utc


class AlertType(enum.Enum):
    late_transfers = 'late_transfers'
    bidi_fastbtc_late_transfers = 'bidi_fastbtc_late_transfers'
    fastbtc_in_late_transfers = 'fastbtc_in_late_transfers'
    other = 'other'


class Alert(Base):
    __tablename__ = 'alert'

    id = Column(Integer, primary_key=True)

    type = Column(Enum(AlertType), nullable=False)

    created_on = Column(TZDateTime, default=now_in_utc, nullable=False)
    last_message_sent_on = Column(TZDateTime, nullable=False)
    resolved = Column(Boolean, nullable=False, default=False)
