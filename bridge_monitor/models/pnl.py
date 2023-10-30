from sqlalchemy import Column, ForeignKey, Integer, Numeric, Text
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import declared_attr, relationship, backref

from .meta import Base
from .types import TZDateTime


class ProfitCalculation(Base):
    """
    Base for transfers that have a PnL calculation. Individual transactions are linked to this.
    """
    __tablename__ = 'pnl_calculation'

    id = Column(Integer, primary_key=True)
    service = Column(Text, nullable=False)  # e.g. bidi_fastbtc, fastbtc_in
    config_chain = Column(Text, nullable=False)  # denormalized. rsk_mainnet/rsk_testnet but never bitcoin. used for filtering
    timestamp = Column(TZDateTime, nullable=False)  # unique timestamp for a transfer, to be used for filtering

    transactions = relationship('PnLTransaction', back_populates='profit_calculation')

    volume_btc = Column(Numeric, nullable=False)  # total amount transferred, including fees
    gross_profit_btc = Column(Numeric, nullable=False)  # fee paid to us (gross profit)
    cost_btc = Column(Numeric, nullable=False)  # cost in btc, decimal value. denormalized because this can be calculated from transfers

    @hybrid_property
    def net_profit_btc(self):
        return self.gross_profit_btc - self.cost_btc


class PnLTransaction(Base):
    __tablename__ = 'pnl_transaction'

    id = Column(Integer, primary_key=True)

    profit_calculation_id = Column(Integer, ForeignKey('pnl_calculation.id'), nullable=False)
    profit_calculation = relationship('ProfitCalculation', back_populates='transactions')

    cost_btc = Column(Numeric, nullable=False)  # cost in btc, decimal value

    transaction_chain = Column(Text, nullable=False)  # can be rsk_mainnet/rsk_testnet but also "bitcoin"
    transaction_id = Column(Text, nullable=False)  # rsk tx hash or bitcoin tx id

    timestamp = Column(TZDateTime, nullable=False)
    block_number = Column(Integer, nullable=True)  # rsk/btc block

    comment = Column(Text, nullable=False, default="", server_default="")


class HasPnL:
    """
    Mixin for transfers that have a PnLTransfer
    """
    @declared_attr
    def profit_calculation_id(cls):
        return Column(Integer, ForeignKey('pnl_calculation.id'), nullable=True)

    @declared_attr
    def profit_calculation(cls):
        backref_name = cls.__tablename__ + 's'
        return relationship(ProfitCalculation, backref=backref(backref_name))

