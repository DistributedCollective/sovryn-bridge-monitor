from pyramid.view import view_config
from sqlalchemy.orm import Session

from bridge_monitor.models.replenisher import BidirectionalFastBTCReplenisherTransaction


@view_config(route_name='replenisher', renderer='bridge_monitor:templates/replenisher.jinja2')
def replenisher(request):
    dbsession: Session = request.dbsession
    chain_env = request.registry.get('chain_env', 'mainnet')
    chain = f'rsk_{chain_env}'

    try:
        max_transactions = int(request.params.get('count', 10))
    except (TypeError, ValueError):
        max_transactions = 10

    bidi_fastbtc_transactions = dbsession.query(
        BidirectionalFastBTCReplenisherTransaction
    ).filter(
        BidirectionalFastBTCReplenisherTransaction.config_chain == chain
    ).order_by(
        BidirectionalFastBTCReplenisherTransaction.block_timestamp.desc()
    ).limit(
        max_transactions
    ).all()

    return {
        'max_transfers': max_transactions,
        'bidi_fastbtc_transactions': bidi_fastbtc_transactions,
    }
