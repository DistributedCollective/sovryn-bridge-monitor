from pyramid.view import view_config
from sqlalchemy.orm import Session

from bridge_monitor.business_logic.key_value_store import KeyValueStore
from bridge_monitor.models.bidirectional_fastbtc import (
    BidirectionalFastBTCTransfer,
    TransferStatus
)


@view_config(route_name='bidirectional_fastbtc', renderer='bridge_monitor:templates/bidirectional_fastbtc.jinja2')
def bidirectional_fastbtc(request):
    dbsession: Session = request.dbsession
    key_value_store = KeyValueStore(dbsession)
    chain_env = request.registry.get('chain_env', 'mainnet')
    chain_name = f'rsk_{chain_env}'

    try:
        max_transfers = int(request.params.get('count', 10))
    except (TypeError, ValueError):
        max_transfers = 10

    transfer_filter_name = request.params.get('filter', '').lower()
    transfer_filter = []
    if transfer_filter_name not in ('unprocessed', 'ignored'):
        transfer_filter_name = ''
    if transfer_filter_name == 'unprocessed':
        transfer_filter = [~BidirectionalFastBTCTransfer.was_processed]
    elif transfer_filter_name == 'ignored':
        transfer_filter = [BidirectionalFastBTCTransfer.ignored]

    ordering = [
        BidirectionalFastBTCTransfer.event_block_timestamp.desc()
    ]

    transfers = dbsession.query(BidirectionalFastBTCTransfer).filter(
        BidirectionalFastBTCTransfer.chain == chain_name
    ).filter(
        *transfer_filter
    ).order_by(*ordering).limit(max_transfers).all()

    return {
        'transfers': transfers,
        'max_transfers': max_transfers,
        'num_transfers': len(transfers),
        'filter_name': transfer_filter_name,
        'btc_explorer_base_url': (
            'https://www.blockchain.com/btc-testnet' if chain_name.endswith('_testnet')
            else 'https://www.blockchain.com/btc'
        ),
        'updated_on': key_value_store.get_value(
            f'bidi-fastbtc:last-updated:{chain_name}',
            None
        ),
    }
