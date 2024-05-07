import csv
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any, List, NamedTuple, Optional

from dateutil.relativedelta import relativedelta
from pyramid.httpexceptions import HTTPBadRequest
from pyramid.request import Request
from pyramid.response import Response
from pyramid.view import view_config
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload
from openpyxl import Workbook
from bridge_monitor.models.pnl import ProfitCalculation
from tempfile import NamedTemporaryFile

class ParsedTimeRange(NamedTuple):
    start: Optional[date]
    end: Optional[date]
    errors: List[str]
    profit_calculation_query_filter: List[Any]


@view_config(route_name='pnl', renderer='bridge_monitor:templates/pnl.jinja2')
def pnl(request: Request):
    dbsession: Session = request.dbsession
    chain_env = request.registry.get('chain_env', 'mainnet')
    chain = f'rsk_{chain_env}'

    start, end, errors, time_filter = _parse_time_range(request)

    calculations_by_service = dbsession.query(
        ProfitCalculation.service,
        func.sum(ProfitCalculation.volume_btc).label('volume_btc'),
        func.sum(ProfitCalculation.gross_profit_btc).label('gross_profit_btc'),
        func.sum(ProfitCalculation.cost_btc).label('cost_btc'),
        func.sum(ProfitCalculation.net_profit_btc).label('net_profit_btc'),
    ).filter(
        ProfitCalculation.config_chain == chain,
        *time_filter,
    ).group_by(
        ProfitCalculation.service,
    ).order_by(
        ProfitCalculation.service,
    ).all()

    earliest_fastbtc_in_timestamp = dbsession.query(
        func.min(ProfitCalculation.timestamp)
    ).filter(
        ProfitCalculation.config_chain == chain,
        ProfitCalculation.service == 'fastbtc_in',
    ).scalar()
    earliest_bidi_fastbtc_timestamp = dbsession.query(
        func.min(ProfitCalculation.timestamp)
    ).filter(
        ProfitCalculation.config_chain == chain,
        ProfitCalculation.service == 'bidi_fastbtc',
    ).scalar()
    earliest_timestamp = min(
        earliest_fastbtc_in_timestamp or datetime.max.replace(tzinfo=timezone.utc),
        earliest_bidi_fastbtc_timestamp or datetime.max.replace(tzinfo=timezone.utc),
    )

    time_filter_options = _get_time_filter_options(earliest_timestamp)

    totals = SimpleNamespace(
        service='TOTAL',
        volume_btc=sum(c.volume_btc for c in calculations_by_service),
        gross_profit_btc=sum(c.gross_profit_btc for c in calculations_by_service),
        cost_btc=sum(c.cost_btc for c in calculations_by_service),
        net_profit_btc=sum(c.net_profit_btc for c in calculations_by_service),
    )

    show_details = request.params.get('show_details') in ('1', 'true')
    if not show_details:
        show_details = bool(start and end and (end - start).days < 100)
    if show_details:
        details = dbsession.query(
            ProfitCalculation,
        ).filter(
            ProfitCalculation.config_chain == chain,
            *time_filter
        ).options(
            joinedload(ProfitCalculation.transactions),
        ).order_by(
            ProfitCalculation.timestamp,
        ).all()
    else:
        details = []

    return {
        'by_service': calculations_by_service,
        'totals': totals,
        'show_details': show_details,
        'details': details,
        'time_filter_options': time_filter_options,
        'start': start,
        'end': end,
        'earliest_timestamps': {
            'fastbtc_in': earliest_fastbtc_in_timestamp,
            'bidi_fastbtc': earliest_bidi_fastbtc_timestamp,
        },
    }


@view_config(route_name='pnl_details')
def pnl_details_excel(request: Request) -> Response:
    dbsession: Session = request.dbsession
    chain_env = request.registry.get('chain_env', 'mainnet')
    chain = f'rsk_{chain_env}'

    parsed_time_range = _parse_time_range(request)
    if parsed_time_range.errors:
        raise HTTPBadRequest(
            'Error generating Table: ' + ', '.join(parsed_time_range.errors)
        )

    response = Response(content_type='application/vnd.ms-excel')
    response.content_disposition = 'attachment;filename=details.xlsx'

    query = dbsession.query(
        ProfitCalculation,
    ).filter(
        ProfitCalculation.config_chain == chain,
        *parsed_time_range.profit_calculation_query_filter
    ).order_by(
        ProfitCalculation.timestamp,
    )

    # Creating the Excel workbook
    wb = Workbook()
    curr_sheet = wb.active
    curr_sheet.title = 'Details'
    curr_sheet.append([
            'time',
            'service',
            'volume_btc',
            'gross_profit_btc',
            'tx_cost_btc',
            'profit_btc',
        ])
    for row in query:
        curr_sheet.append([
            row.timestamp.isoformat(),
            row.service,
            row.volume_btc,
            row.gross_profit_btc,
            row.cost_btc,
            row.net_profit_btc,
        ])
    with NamedTemporaryFile() as tmp:
        wb.save(tmp.name)
        tmp.seek(0)
        response.body = tmp.read()
        return response


@view_config(route_name='pnl_details_csv')
def pnl_details_csv(request: Request):
    dbsession: Session = request.dbsession
    chain_env = request.registry.get('chain_env', 'mainnet')
    chain = f'rsk_{chain_env}'

    parsed_time_range = _parse_time_range(request)
    if parsed_time_range.errors:
        raise HTTPBadRequest(
            'Error generating CSV: ' + ', '.join(parsed_time_range.errors)
        )

    response = Response(content_type='text/csv')
    #response.content_disposition = 'attachment;filename=details.csv'

    query = dbsession.query(
        ProfitCalculation,
    ).filter(
        ProfitCalculation.config_chain == chain,
        *parsed_time_range.profit_calculation_query_filter
    ).order_by(
        ProfitCalculation.timestamp,
    )

    writer = csv.DictWriter(
        response.body_file,
        fieldnames=[
            'time',
            'service',
            'volume_btc',
            'gross_profit_btc',
            'tx_cost_btc',
            'profit_btc',
        ]
    )
    writer.writeheader()
    for row in query:
        writer.writerow({
            'time': row.timestamp.isoformat(),
            'service': row.service,
            'volume_btc': row.volume_btc,
            'gross_profit_btc': row.gross_profit_btc,
            'tx_cost_btc': row.cost_btc,
            'profit_btc': row.net_profit_btc,
        })
    return response


def _parse_time_range(request: Request) -> ParsedTimeRange:
    errors = []
    start = None
    end = None
    try:
        if start_str := request.params.get('start'):
            start = date.fromisoformat(start_str)
    except TypeError:
        errors.append('Invalid start date')
    try:
        if end_str := request.params.get('end'):
            end = date.fromisoformat(end_str)
    except TypeError:
        errors.append('Invalid end date')

    time_filter = []
    if start:
        time_filter.append(
            ProfitCalculation.timestamp >= datetime(start.year, start.month, start.day, tzinfo=timezone.utc)
        )
    if end:
        time_filter.append(
            ProfitCalculation.timestamp < datetime(end.year, end.month, end.day, tzinfo=timezone.utc) + timedelta(days=1)
        )

    return ParsedTimeRange(
        start=start,
        end=end,
        errors=errors,
        profit_calculation_query_filter=time_filter,
    )



def _get_time_filter_options(earliest_timestamp: datetime):
    current_timestamp = datetime.now(timezone.utc)
    time_filter_options = [
        {
            'label': 'ALL',
            'query': {},
        }
    ]
    while current_timestamp >= earliest_timestamp.replace(day=1, hour=0, minute=0, second=0, microsecond=0):
        start = current_timestamp.replace(day=1).date()
        end = start + relativedelta(months=1, days=-1)
        time_filter_options.append({
            'query': {
                'start': start.isoformat(),
                'end': end.isoformat(),
            },
            'label': start.strftime('%b %Y'),
        })
        current_timestamp -= relativedelta(months=1)
    return time_filter_options
