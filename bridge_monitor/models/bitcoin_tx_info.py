from sqlalchemy import Column, Text, Integer, ForeignKey, DateTime, Numeric
from sqlalchemy.orm import relationship

from .meta import Base


class BtcWallet(Base):
    __tablename__ = "btc_wallet"

    id = Column(Integer, primary_key=True)
    name = Column(Text, nullable=False)
    description = Column(Text, nullable=True)
    transactions = relationship(
        "BtcWalletTransaction", lazy="dynamic", back_populates="wallet"
    )


class BtcWalletTransaction(Base):
    __tablename__ = "btc_wallet_transaction"

    wallet_id = Column(
        Integer, ForeignKey("btc_wallet.id"), nullable=False, primary_key=True
    )
    tx_hash = Column(Text, primary_key=True, nullable=False)
    timestamp = Column(DateTime(timezone=True), nullable=False)
    net_change = Column(Numeric(40, 32), nullable=False)
    amount_sent = Column(Numeric(40, 32), nullable=False)
    amount_received = Column(Numeric(40, 32), nullable=False)
    amount_fees = Column(Numeric(40, 32), nullable=False)
    tx_type = Column(Text, nullable=True)
    notes = Column(Text, nullable=True)
    block_height = Column(Integer, nullable=True)
    wallet = relationship(BtcWallet)
