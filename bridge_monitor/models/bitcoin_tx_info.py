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
    pending_transactions = relationship(
        "PendingBtcWalletTransaction", lazy="dynamic", back_populates="wallet"
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


class PendingBtcWalletTransaction(Base):
    __tablename__ = "pending_btc_wallet_transaction"

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

    def to_complete(self):
        return BtcWalletTransaction(
            wallet=self.wallet,
            tx_hash=self.tx_hash,
            timestamp=self.timestamp,
            net_change=self.net_change,
            amount_sent=self.amount_sent,
            amount_received=self.amount_received,
            amount_fees=self.amount_fees,
            tx_type=None,
            notes=self.notes,
            block_height=self.block_height,
        )
