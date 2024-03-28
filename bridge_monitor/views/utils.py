from datetime import (
    date,
    datetime,
    timedelta,
    timezone,
)
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


class ParsedTimeRange(NamedTuple):
    start: Optional[date]
    end: Optional[date]
    errors: List[str]
    query_filters_by_model: Dict[Any, List[Any]]


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

    time_filters_by_model = {}
    for model in models:
        time_filter = []
        if start:
            time_filter.append(
                model.timestamp >= datetime(start.year, start.month, start.day, tzinfo=timezone.utc)
            )
        if end:
            time_filter.append(
                model.timestamp < datetime(end.year, end.month, end.day, tzinfo=timezone.utc) + timedelta(days=1)
            )
        time_filters_by_model[model] = time_filter

    return ParsedTimeRange(
        start=start,
        end=end,
        errors=errors,
        query_filters_by_model=time_filters_by_model,
    )
