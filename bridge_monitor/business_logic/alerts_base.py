import logging
from datetime import timedelta
from textwrap import dedent

import transaction

from .messages import Messager
from ..models import Alert, AlertType, get_tm_session
from ..models.types import now_in_utc

logger = logging.getLogger(__name__)


def handle_late_transfer_alerts(
    *,
    session_factory,
    alert_type: AlertType,
    transaction_manager: transaction.TransactionManager = transaction.manager,
    alert_interval: timedelta = timedelta(minutes=30),
    alert_source: str,
    messager: Messager,
    num_late_transfers: int,
):
    """
    Base method that handles late transfer alerts for both the token bridge and bidirectional fastbtc
    (and others to come)
    """
    logger.info(f"Handling alerts ({alert_type})")

    with transaction_manager as tx:
        dbsession = get_tm_session(
            session_factory,
            transaction_manager,
        )

        # There should be 0-1 of these, but in principle it's possible that there are multiple
        existing_alerts = (
            dbsession.query(Alert)
            .filter_by(
                type=alert_type,
                resolved=False,
            )
            .all()
        )

        now = now_in_utc()

        # Determine actions to take
        send_alert_message = False
        resolve_alerts = False
        if num_late_transfers:
            if not existing_alerts:
                send_alert_message = True
            else:
                last_message_sent_on = max(
                    a.last_message_sent_on for a in existing_alerts
                )
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
                dbsession.add(
                    Alert(
                        type=alert_type,
                        last_message_sent_on=now_in_utc(),
                    )
                )

            def send_alert_message_after_commit(success, num):
                if success:
                    messager.send_message(
                        dedent(f"""\
                    **🚨 Alert! 🚨**
                    There are **{num}** late transfers on {alert_source}. (ping <@815287495796326445> <@338385028570546177>)
                    """)
                    )
                else:
                    logger.error("Transaction failure, not sending message")

            tx.addAfterCommitHook(
                send_alert_message_after_commit, args=(num_late_transfers,)
            )

        if resolve_alerts:
            logger.info("Resolving existing alerts")
            for a in existing_alerts:
                a.resolved = True

            def send_resolved_message_after_commit(success):
                if success:
                    messager.send_message(
                        f"**Resolved:** No more late transfers on {alert_source} 😌 ."
                    )
                else:
                    logger.error("Transaction failure, not sending message")

            tx.addAfterCommitHook(send_resolved_message_after_commit)

    logger.info("Alerts handled.")
