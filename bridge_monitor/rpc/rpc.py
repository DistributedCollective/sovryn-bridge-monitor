import os
from datetime import datetime, timezone
from decimal import Decimal, getcontext
import logging
from typing import List, Any, Optional

import requests
import dotenv
from sqlalchemy import select
from sqlalchemy.orm import Session
from bridge_monitor.models.bitcoin_tx_info import (
    BtcWallet,
    BtcWalletTransaction,
    PendingBtcWalletTransaction,
)
from sqlalchemy.sql import func

logger = logging.getLogger(__name__)

dotenv.load_dotenv()
RPC_USER = os.getenv("RPC_USER")
RPC_PASSWORD = os.getenv("RPC_PASSWORD")
RPC_URL = os.getenv("RPC_URL")

getcontext().prec = 32


def send_rpc_request(
    method: str, params: List[Any], url: str, id: str = "test"
) -> requests.Response:
    return requests.post(
        url,
        json={"jsonrpc": "2.0", "id": id, "method": method, "params": params},
        auth=(RPC_USER, RPC_PASSWORD),
        headers={"content-type": "plain/text"},
    )


def get_block_hash(block_n: int, wallet_url):
    block_response = send_rpc_request(
        "getblockstats", [block_n, ["height", "blockhash"]], wallet_url
    ).json()
    return block_response["result"]["blockhash"]


def get_wallet_transactions_from_block(
    dbsession: Session, block_n: int, wallet_name: str, safety_limit: int = 5
):
    logger.info(
        "Searching for transaction from block: %d on wallet: %s", block_n, wallet_name
    )
    main_request_params = []

    wallet = dbsession.query(BtcWallet).filter(BtcWallet.name == wallet_name).first()
    if wallet is None:
        logger.info("Wallet with name %s not found in db", wallet_name)
        logger.info("Adding wallet %s into db", wallet_name)
        wallet = BtcWallet(name=wallet_name)

    wallet_url = f"{RPC_URL}/wallet/{wallet_name}"

    if block_n > 0:
        block_response = send_rpc_request(
            "getblockstats", [block_n, ["height", "blockhash"]], wallet_url
        ).json()
        main_request_params.append(block_response["result"]["blockhash"])

    response = send_rpc_request(
        "listsinceblock", main_request_params, wallet_url
    ).json()
    results = response["result"]["transactions"]

    curr_block_height = send_rpc_request("getblockcount", [], RPC_URL).json()["result"]

    if not results:
        logger.info("Found no transactions since block %d", block_n)
        return

    logger.info("Results found: %d", len(results))
    prev_tx_hash = ""
    transaction: Optional[BtcWalletTransaction | PendingBtcWalletTransaction] = None

    for entry in results:
        if entry["txid"] != prev_tx_hash:
            if (
                entry.get("blockheight") is None
                or entry.get("blockheight") + safety_limit > curr_block_height
            ):
                transaction = PendingBtcWalletTransaction(
                    wallet=wallet,
                    tx_hash=entry["txid"],
                    block_height=entry.get("blockheight", None),
                    timestamp=datetime.fromtimestamp(entry["time"], tz=timezone.utc),
                    net_change=Decimal(),
                    amount_sent=Decimal(),
                    amount_received=Decimal(),
                    amount_fees=Decimal(),
                )

                # check if transaction is already marked as pending in db
                if (
                    dbsession.execute(
                        select(PendingBtcWalletTransaction.wallet_id).where(
                            PendingBtcWalletTransaction.tx_hash == entry["txid"],
                            PendingBtcWalletTransaction.wallet_id == wallet.id,
                        )
                    ).scalar_one_or_none()
                    is not None
                ):
                    continue

            else:
                pending_entry: Optional[PendingBtcWalletTransaction] = (
                    dbsession.execute(
                        select(PendingBtcWalletTransaction).where(
                            PendingBtcWalletTransaction.tx_hash == entry["txid"],
                            PendingBtcWalletTransaction.wallet_id == wallet.id,
                        )
                    ).scalar()
                )
                if pending_entry is not None:
                    logger.info("expungin entry %s", pending_entry.tx_hash)
                    transaction = pending_entry.to_complete()
                    transaction.block_height = entry["blockheight"]
                    dbsession.delete(pending_entry)
                else:
                    transaction = BtcWalletTransaction(
                        wallet=wallet,
                        tx_hash=entry["txid"],
                        block_height=entry["blockheight"],
                        timestamp=datetime.fromtimestamp(
                            entry["time"], tz=timezone.utc
                        ),
                        net_change=Decimal(),
                        amount_sent=Decimal(),
                        amount_received=Decimal(),
                        amount_fees=Decimal(),
                    )
            dbsession.add(transaction)
        if entry["category"] == "send":
            transaction.amount_sent += -Decimal(str(entry["amount"]))
            transaction.amount_fees = -Decimal(str(entry["fee"]))
        elif entry["category"] == "receive":
            transaction.amount_received += Decimal(str(entry["amount"]))
        else:
            raise ValueError(f"Unknown transaction type {entry['category']}")

        prev_tx_hash = entry["txid"]
        transaction.net_change = (
            transaction.amount_received
            - transaction.amount_sent
            - transaction.amount_fees
        )
    dbsession.flush()


def get_new_btc_transactions(dbsession: Session, wallet_name: str) -> None:
    logger.info("Searching for new blocks")

    newest_block_n = (
        dbsession.query(func.max(BtcWalletTransaction.block_height))
        .filter(BtcWalletTransaction.wallet.has(name=wallet_name))
        .scalar()
    )
    if newest_block_n is None:
        newest_block_n = 1
    get_wallet_transactions_from_block(dbsession, newest_block_n, wallet_name)


def get_btc_wallet_balance_at_date(
    dbsession: Session, wallet_name: str, target_date: datetime
) -> Decimal:
    logger.info("Getting %s balance at %s", wallet_name, target_date.isoformat())
    newest_tx = (
        dbsession.query(BtcWalletTransaction)
        .filter(BtcWalletTransaction.wallet.has(name=wallet_name))
        .order_by(BtcWalletTransaction.timestamp.desc())
        .first()
    )
    if newest_tx is None:
        logger.info("Btc wallet tx table has no entries for wallet %s", wallet_name)
        get_new_btc_transactions(dbsession, wallet_name)
    elif target_date > newest_tx.timestamp:
        logger.info(
            "Newest transaction timestamp older than requested, fetching new transactions"
        )
        get_new_btc_transactions(dbsession, wallet_name)
    sum_of_transactions = (
        dbsession.query(func.sum(BtcWalletTransaction.net_change))
        .filter(
            BtcWalletTransaction.timestamp < target_date,
            BtcWalletTransaction.wallet.has(name=wallet_name),
        )
        .scalar()
    )
    logger.info(
        "Balance for %s at %s is %s", wallet_name, target_date, sum_of_transactions
    )
    return sum_of_transactions
