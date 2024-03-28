import json
from datetime import (
    date,
    datetime,
    timedelta,
    timezone,
)
from decimal import Decimal
from typing import (
    Any,
    Dict,
    Iterable,
    List,
    Literal,
    NamedTuple,
    Optional,
    Tuple,
    Union,
)

from pyramid.request import Request


class JsonEncoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, Decimal):
            return str(o)
        if isinstance(o, (datetime, date)):
            return o.isoformat()
        return super().default(o)



class ParsedTimeRange(NamedTuple):
    start: Optional[date]
    end: Optional[date]
    errors: List[str]


def parse_time_range(
    *,
    request: Request,
    models: Iterable[Any] = tuple(),  # List of Models
    default: Union[Tuple[datetime, datetime], Literal['this_month'], None] =None
) -> ParsedTimeRange:
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

    if default == 'this_month' and (not start and not end):
        now = datetime.now(tz=timezone.utc)
        start = date(now.year, now.month, 1)
        end = date(now.year, now.month + 1, 1) - timedelta(days=1)

    return ParsedTimeRange(
        start=start,
        end=end,
        errors=errors,
    )
