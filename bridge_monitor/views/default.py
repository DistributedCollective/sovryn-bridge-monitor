from pyramid.view import view_config
from sqlalchemy.orm import Session

from bridge_monitor.business_logic.key_value_store import KeyValueStore
from bridge_monitor.models import Transfer


@view_config(
    route_name="bridge_transfers",
    renderer="bridge_monitor:templates/bridge_transfers.jinja2",
)
def bridge_transfers(request):
    dbsession: Session = request.dbsession
    key_value_store = KeyValueStore(dbsession)
    chain_env = request.registry.get("chain_env", "mainnet")

    try:
        max_transfers = int(request.params.get("count", 10))
    except (TypeError, ValueError):
        max_transfers = 10

    transfer_filter_name = request.params.get("filter", "").lower()
    transfer_filter = []
    if transfer_filter_name not in ("unprocessed", "ignored"):
        transfer_filter_name = ""
    if transfer_filter_name == "unprocessed":
        transfer_filter = [~Transfer.was_processed]
    elif transfer_filter_name == "ignored":
        transfer_filter = [Transfer.ignored]

    symbols = request.params.get("symbols", None)
    if symbols:
        symbols = symbols.split(",")
        transfer_filter.append(Transfer.token_symbol.in_(symbols))

    time_taken_gte = request.params.get("time_taken_gte", None)
    if time_taken_gte:
        time_taken_gte = int(time_taken_gte)
        transfer_filter.append(
            Transfer.seconds_from_deposit_to_execution >= time_taken_gte
        )

    ordering = [Transfer.event_block_timestamp.desc()]

    rsk_eth_transfers = (
        dbsession.query(Transfer)
        .filter(
            (
                (
                    (Transfer.from_chain == f"rsk_{chain_env}")
                    & (Transfer.to_chain == f"eth_{chain_env}")
                )
                | (
                    (Transfer.from_chain == f"eth_{chain_env}")
                    & (Transfer.to_chain == f"rsk_{chain_env}")
                )
            )
        )
        .filter(*transfer_filter)
        .order_by(*ordering)
        .limit(max_transfers)
        .all()
    )

    rsk_bsc_transfers = (
        dbsession.query(Transfer)
        .filter(
            (
                (
                    (Transfer.from_chain == f"rsk_{chain_env}")
                    & (Transfer.to_chain == f"bsc_{chain_env}")
                )
                | (
                    (Transfer.from_chain == f"bsc_{chain_env}")
                    & (Transfer.to_chain == f"rsk_{chain_env}")
                )
            )
        )
        .filter(*transfer_filter)
        .order_by(*ordering)
        .limit(max_transfers)
        .all()
    )

    last_updated = {
        "rsk_eth": key_value_store.get_value(f"last-updated:rsk_eth_{chain_env}", None),
        "rsk_bsc": key_value_store.get_value(f"last-updated:rsk_bsc_{chain_env}", None),
    }

    return {
        "transfers_by_bridge": {
            "rsk_eth": rsk_eth_transfers,
            "rsk_bsc": rsk_bsc_transfers,
        },
        "max_transfers": max_transfers,
        "last_updated_by_bridge": last_updated,
        "filter_name": transfer_filter_name,
    }
