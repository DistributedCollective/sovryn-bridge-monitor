from logging import getLogger
from typing import Optional, Sequence

from pyramid.view import view_config
from sqlalchemy.sql import select

from ..models import LedgerDescriptionOverride

logger = getLogger(__name__)


@view_config(
    route_name="descriptions", renderer="bridge_monitor:templates/descriptions.jinja2"
)
def descriptions(request):
    if request.method == "POST":
        tx_hash: Optional[str] = request.POST.get("tx_hash")
        description: Optional[str] = request.POST.get("description")
        if not tx_hash:
            raise ValueError("tx_hash is required")

        existing_entry: Optional[LedgerDescriptionOverride] = request.dbsession.execute(
            select(LedgerDescriptionOverride).where(
                LedgerDescriptionOverride.tx_hash == tx_hash
            )
        ).scalar_one_or_none()

        if existing_entry and description:  # update
            existing_entry.description_override = description

        elif existing_entry and not description:  # delete
            request.dbsession.delete(existing_entry)

        elif existing_entry is None and description:  # insert
            request.dbsession.add(
                LedgerDescriptionOverride(
                    tx_hash=tx_hash, description_override=description
                )
            )

        request.dbsession.flush()

    overrides: Sequence[LedgerDescriptionOverride] = (
        request.dbsession.execute(select(LedgerDescriptionOverride)).scalars().all()
    )
    return {
        "overrides": overrides,
    }
