import logging
from datetime import timedelta
from typing import Optional

import transaction

from .alerts_base import handle_late_transfer_alerts
from .messages import get_preferred_messager
from ..models import AlertType, Transfer, get_tm_session

logger = logging.getLogger(__name__)


def handle_bridge_alerts(
    *,
    session_factory,
    transaction_manager: transaction.TransactionManager = transaction.manager,
    alert_interval: timedelta = timedelta(minutes=30),
    discord_webhook_url: Optional[str] = None,
):
    messager = get_preferred_messager(
        discord_webhook_url=discord_webhook_url, username="Bridge Monitor"
    )

    with transaction_manager:
        dbsession = get_tm_session(
            session_factory,
            transaction_manager,
        )
        late_transfers = (
            dbsession.query(Transfer)
            .filter(Transfer.is_late() & ~Transfer.ignored)
            .all()
        )

    # This needs to be called even if there are no late transfers, to clear up existing alerts
    handle_late_transfer_alerts(
        session_factory=session_factory,
        transaction_manager=transaction_manager,
        alert_interval=alert_interval,
        alert_source="the token bridge",
        alert_type=AlertType.late_transfers,
        num_late_transfers=len(late_transfers),
        messager=messager,
    )
