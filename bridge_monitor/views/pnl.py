from types import SimpleNamespace
from pyramid.view import view_config
from sqlalchemy.orm import Session
from sqlalchemy import func


from bridge_monitor.models.pnl import ProfitCalculation, PnLTransaction
from bridge_monitor.business_logic.key_value_store import KeyValueStore

@view_config(route_name='pnl', renderer='bridge_monitor:templates/pnl.jinja2')
def pnl(request):
    dbsession: Session = request.dbsession
    chain_env = request.registry.get('chain_env', 'mainnet')
    chain = f'rsk_{chain_env}'

    calculations_by_service = dbsession.query(
        ProfitCalculation.service,
        func.sum(ProfitCalculation.volume_btc).label('volume_btc'),
        func.sum(ProfitCalculation.gross_profit_btc).label('gross_profit_btc'),
        func.sum(ProfitCalculation.cost_btc).label('cost_btc'),
        func.sum(ProfitCalculation.net_profit_btc).label('net_profit_btc'),
    ).filter(
        ProfitCalculation.config_chain == chain,
    ).group_by(
        ProfitCalculation.service,
    ).order_by(
        ProfitCalculation.service,
    ).all()

    totals = SimpleNamespace(
        service='TOTAL',
        volume_btc=sum(c.volume_btc for c in calculations_by_service),
        gross_profit_btc=sum(c.gross_profit_btc for c in calculations_by_service),
        cost_btc=sum(c.cost_btc for c in calculations_by_service),
        net_profit_btc=sum(c.net_profit_btc for c in calculations_by_service),
    )

    return {
        'by_service': calculations_by_service,
        'totals': totals,
    }