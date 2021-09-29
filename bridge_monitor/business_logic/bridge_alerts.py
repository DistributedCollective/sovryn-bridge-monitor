from datetime import timedelta
import logging
from textwrap import dedent
from typing import Optional

import transaction

from ..models import Transfer, Alert, AlertType, get_tm_session
from ..models.types import now_in_utc
from .messages import get_preferred_messager

logger = logging.getLogger(__name__)


def handle_bridge_alerts(
    *,
    session_factory,
    transaction_manager: transaction.TransactionManager = transaction.manager,
    alert_interval: timedelta = timedelta(minutes=30),
    discord_webhook_url: Optional[str] = None,
):
    logger.info("Handling alerts")

    messager = get_preferred_messager(
        discord_webhook_url=discord_webhook_url,
        username="Bridge Monitor"
    )

    with transaction_manager as tx:
        dbsession = get_tm_session(
            session_factory,
            transaction_manager,
        )
        late_transfers = dbsession.query(Transfer).filter(
            Transfer.is_late() & ~Transfer.ignored
        ).all()

        # There should be 0-1 of these, but in principle it's possible that there are multiple
        existing_alerts = dbsession.query(Alert).filter_by(
            type=AlertType.late_transfers,
            resolved=False,
        ).all()

        now = now_in_utc()

        # Determine actions to take
        send_alert_message = False
        resolve_alerts = False
        if late_transfers:
            if not existing_alerts:
                send_alert_message = True
            else:
                last_message_sent_on = max(a.last_message_sent_on for a in existing_alerts)
                send_alert_message = now - last_message_sent_on > alert_interval
        else:
            if existing_alerts:
                resolve_alerts = True

        if send_alert_message:
            logger.info("Sending alert message")
            if existing_alerts:
                for a in existing_alerts:
                    a.last_message_sent_on = now
            else:
                dbsession.add(Alert(
                    type=AlertType.late_transfers,
                    last_message_sent_on=now_in_utc(),
                ))

            def send_alert_message_after_commit(success, num_late_transfers):
                if success:
                    messager.send_message(dedent(f"""\
                    **🚨 Alert! 🚨**
                    There are **{num_late_transfers}** late transfers on the token bridge.
                    """))
                else:
                    logger.error("Transaction failure, not sending message")
            tx.addAfterCommitHook(send_alert_message_after_commit, args=(len(late_transfers),))

        if resolve_alerts:
            logger.info("Resolving existing alerts")
            for a in existing_alerts:
                a.resolved = True

            def send_resolved_message_after_commit(success):
                if success:
                    messager.send_message("**Resolved:** No more late transfers on the token bridge 😌 .")
                else:
                    logger.error("Transaction failure, not sending message")
            tx.addAfterCommitHook(send_resolved_message_after_commit)

    logger.info("Alerts handled.")