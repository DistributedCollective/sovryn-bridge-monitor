from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import Column, Integer, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.hybrid import hybrid_property

from .pnl import HasPnL
from .meta import Base
from .types import TZDateTime, Uint256, now_in_utc

SATOSHI_IN_BTC = 100_000_000


class BidirectionalFastBTCReplenisherTransaction(HasPnL, Base):
    __tablename__ = "bidi_fastbtc_replenisher_transaction"

    id = Column(Integer, primary_key=True)

    config_chain = Column(Text, nullable=False)
    transaction_chain = Column(Text, nullable=False)

    transaction_id = Column(Text, nullable=True)
    block_number = Column(Integer, nullable=True)
    block_timestamp = Column(Integer, nullable=True)

    fee_satoshi = Column(Uint256, nullable=False)
    amount_satoshi = Column(Uint256, nullable=False)

    seen_on = Column(TZDateTime, default=now_in_utc, nullable=False)
    updated_on = Column(TZDateTime, default=now_in_utc, nullable=False)

    raw_data = Column(JSONB, default=dict, server_default="{}", nullable=False)

    @hybrid_property
    def amount_btc(self):
        return Decimal(self.amount_satoshi) / SATOSHI_IN_BTC

    @hybrid_property
    def fee_btc(self):
        return Decimal(self.fee_satoshi) / SATOSHI_IN_BTC

    @hybrid_property
    def confirmed_on(self):
        return datetime.utcfromtimestamp(self.block_timestamp).replace(
            tzinfo=timezone.utc
        )
