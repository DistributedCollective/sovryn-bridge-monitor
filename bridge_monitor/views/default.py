from pyramid.view import view_config
from sqlalchemy.orm import Session

from bridge_monitor.business_logic.key_value_store import KeyValueStore
from bridge_monitor.models import Transfer


@view_config(route_name='bridge_transfers', renderer='bridge_monitor:templates/bridge_transfers.jinja2')
def bridge_transfers(request):
    dbsession: Session = request.dbsession
    key_value_store = KeyValueStore(dbsession)

    try:
        max_transfers = int(request.params.get('count', 10))
    except (TypeError, ValueError):
        max_transfers = 10

    transfer_filter_name = request.params.get('filter', '').lower()
    transfer_filter = []
    if transfer_filter_name not in ('unprocessed', 'ignored'):
        transfer_filter_name = ''
    if transfer_filter_name == 'unprocessed':
        transfer_filter = [~Transfer.was_processed]
    elif transfer_filter_name == 'ignored':
        transfer_filter = [Transfer.ignored]

    ordering = [Transfer.event_block_timestamp.desc()]

    rsk_eth_transfers = dbsession.query(Transfer).filter(
        (((Transfer.from_chain == 'rsk_mainnet') & (Transfer.to_chain == 'eth_mainnet')) |
         ((Transfer.from_chain == 'eth_mainnet') & (Transfer.to_chain == 'rsk_mainnet')))
    ).filter(
        *transfer_filter
    ).order_by(*ordering).limit(max_transfers).all()

    rsk_bsc_transfers = dbsession.query(Transfer).filter(
        (((Transfer.from_chain == 'rsk_mainnet') & (Transfer.to_chain == 'bsc_mainnet')) |
         ((Transfer.from_chain == 'bsc_mainnet') & (Transfer.to_chain == 'rsk_mainnet')))
    ).filter(
        *transfer_filter
    ).order_by(*ordering).limit(max_transfers).all()

    last_updated = {
        'rsk_eth': key_value_store.get_value('last-updated:rsk_eth_mainnet', None),
        'rsk_bsc': key_value_store.get_value('last-updated:rsk_bsc_mainnet', None),
    }

    return {
        'transfers_by_bridge': {
            'rsk_eth': rsk_eth_transfers,
            'rsk_bsc': rsk_bsc_transfers,
        },
        'max_transfers': max_transfers,
        'last_updated_by_bridge': last_updated,
        'filter_name': transfer_filter_name,
    }
