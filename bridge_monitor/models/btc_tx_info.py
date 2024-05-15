from sqlalchemy import (
    Column,
    Text,
    Integer,
    ForeignKey,
    DateTime,
    DECIMAL
)


from .meta import Base


class BtcWallet(Base):
    __tablename__ = 'btc_wallet'

    id = Column(Integer, primary_key=True)
    name = Column(Text, nullable=False)


class BtcWalletTransaction(Base):
    __tablename__ = 'btc_wallet_transaction'

    wallet_id = Column(Integer, ForeignKey('btc_wallet.id'), nullable=False, primary_key=True)
    tx_hash = Column(Text, primary_key=True, nullable=False)
    block_height = Column(Integer, nullable=False)
    timestamp = Column(DateTime(timezone=True), nullable=False)
    net_change = Column(DECIMAL(40, 30), nullable=False)
    amount_sent = Column(DECIMAL(40, 30), nullable=False)
    amount_received = Column(DECIMAL(40, 30), nullable=False)
    amount_fees = Column(DECIMAL(40, 30), nullable=False)



