import os
from datetime import datetime, timezone
from decimal import Decimal, getcontext
import logging
from itertools import groupby
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


def get_wallet_transactions_from_block(
    dbsession: Session, block_n: int, wallet_name: str, safety_limit: int = 5
):
    if RPC_URL is None:
        logger.error("No bitcoin rpc url specified")
        return
    logger.debug(
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
        logger.debug("Found no transactions since block %d", block_n)
        return
    temp_results = []

    # sum all duplicate transactions
    for k, v in groupby(
        sorted(results, key=lambda x: (x["txid"], x.get("vout", -1))),
        lambda x: (x["txid"], x.get("vout", -1)),
    ):
        v = list(v)
        if len(v) < 2:
            temp_results.append(v[0])
            continue
        v[0]["amount"] = sum([Decimal(str(x["amount"])) for x in v])
        if v[0]["amount"] != Decimal("0"):
            temp_results.append(v[0])

    results = temp_results

    transaction: Optional[BtcWalletTransaction | PendingBtcWalletTransaction] = None
    logger.debug("Results found: %d", len(results))
    for entry in temp_results:
        if (
            entry.get("blockheight") is None
            or entry.get("blockheight") + safety_limit > curr_block_height
        ):
            transaction = PendingBtcWalletTransaction(
                wallet=wallet,
                tx_hash=entry["txid"],
                vout=entry.get("vout", -1),
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
                        PendingBtcWalletTransaction.vout == entry.get("vout", -1),
                    )
                ).scalar_one_or_none()
                is not None
            ):
                continue

        else:
            pending_entry: Optional[PendingBtcWalletTransaction] = dbsession.execute(
                select(PendingBtcWalletTransaction).where(
                    PendingBtcWalletTransaction.tx_hash == entry["txid"],
                    PendingBtcWalletTransaction.wallet_id == wallet.id,
                    PendingBtcWalletTransaction.vout == entry.get("vout", -1),
                )
            ).scalar()
            if pending_entry is not None:
                transaction = pending_entry.to_complete()
                transaction.block_height = entry["blockheight"]
                dbsession.delete(pending_entry)
            else:
                transaction = BtcWalletTransaction(
                    wallet=wallet,
                    tx_hash=entry["txid"],
                    vout=entry.get("vout", -1),
                    block_height=entry["blockheight"],
                    timestamp=datetime.fromtimestamp(entry["time"], tz=timezone.utc),
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

        transaction.net_change = (
            transaction.amount_received
            - transaction.amount_sent
            - transaction.amount_fees
        )
    dbsession.flush()


def get_new_btc_transactions(dbsession: Session, wallet_name: str) -> None:
    logger.debug("Searching for new blocks")

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
        logger.debug(
            "Newest transaction timestamp older than requested, fetching new transactions"
        )
        get_new_btc_transactions(dbsession, wallet_name)

    target_wallet_id = dbsession.execute(select(BtcWallet.id).where(BtcWallet.name == wallet_name)).scalar()

    full_transaction_subquery = (
        select(
                BtcWalletTransaction.tx_hash,
                func.max(BtcWalletTransaction.timestamp).label("timestamp"),
                BtcWalletTransaction.wallet_id,
                (func.sum(BtcWalletTransaction.amount_received)
                    - func.sum(BtcWalletTransaction.amount_sent)
                    - func.max(BtcWalletTransaction.amount_fees)).label("net_change"),
                func.sum(BtcWalletTransaction.amount_received).label("amount_received"),
                func.sum(BtcWalletTransaction.amount_sent).label("amount_sent"),
                func.max(BtcWalletTransaction.amount_fees).label("amount_fees")
        ).group_by(BtcWalletTransaction.tx_hash, BtcWalletTransaction.wallet_id).subquery())

    sum_of_transactions = dbsession.execute(
        select(func.sum(full_transaction_subquery.c.net_change)).where(
            full_transaction_subquery.c.timestamp <= target_date,
            full_transaction_subquery.c.wallet_id == target_wallet_id
        )
    ).scalar()

    logger.info(
        "Balance for %s at %s is %s", wallet_name, target_date, sum_of_transactions
    )
    return sum_of_transactions if sum_of_transactions is not None else Decimal(0)
