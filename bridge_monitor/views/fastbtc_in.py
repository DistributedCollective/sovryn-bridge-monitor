from pyramid.view import view_config
from sqlalchemy.orm import Session

from bridge_monitor.business_logic.key_value_store import KeyValueStore
from bridge_monitor.models.fastbtc_in import FastBTCInTransfer


@view_config(
    route_name="fastbtc_in", renderer="bridge_monitor:templates/fastbtc_in.jinja2"
)
def fastbtc_in(request):
    dbsession: Session = request.dbsession
    key_value_store = KeyValueStore(dbsession)
    chain_env = request.registry.get("chain_env", "mainnet")
    chain_name = f"rsk_{chain_env}"

    try:
        max_transfers = int(request.params.get("count", 10))
    except (TypeError, ValueError):
        max_transfers = 10

    transfer_filter_name = request.params.get("filter", "").lower()
    transfer_filter = []
    if transfer_filter_name not in ("unprocessed", "ignored"):
        transfer_filter_name = ""
    if transfer_filter_name == "unprocessed":
        transfer_filter = [~FastBTCInTransfer.was_processed]
    elif transfer_filter_name == "ignored":
        transfer_filter = [FastBTCInTransfer.ignored]

    ordering = [FastBTCInTransfer.submission_block_timestamp.desc()]

    transfers = (
        dbsession.query(FastBTCInTransfer)
        .filter(FastBTCInTransfer.chain == chain_name)
        .filter(*transfer_filter)
        .order_by(*ordering)
        .limit(max_transfers)
        .all()
    )

    return {
        "transfers": transfers,
        "max_transfers": max_transfers,
        "num_transfers": len(transfers),
        "filter_name": transfer_filter_name,
        "btc_explorer_base_url": (
            "https://www.blockchain.com/btc-testnet"
            if chain_name.endswith("_testnet")
            else "https://www.blockchain.com/btc"
        ),
        "rsk_explorer_base_url": (
            "https://explorer.testnet.rsk.co"
            if chain_name.endswith("_testnet")
            else "https://explorer.rsk.co"
        ),
        "updated_on": key_value_store.get_value(
            f"fastbtc-in:last-updated:{chain_name}", None
        ),
    }
