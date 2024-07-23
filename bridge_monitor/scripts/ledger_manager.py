from datetime import datetime, timezone
import logging

from sqlalchemy import text
from sqlalchemy.orm import Session

from bridge_monitor.models.ledger_meta import LedgerUpdate

SCRIPT_NAME = "create_ledger.sql"

logger = logging.getLogger(__name__)


def create_ledger(dbsession: Session):
    error = None
    try:
        ledger_script = text(open(SCRIPT_NAME).read())
        logger.info("running %s script", SCRIPT_NAME)
        dbsession.execute(ledger_script)
    except Exception as e:
        logger.error("error running %s script: %s", SCRIPT_NAME, e)
        error = str(e)
    finally:
        update = LedgerUpdate(
            timestamp=datetime.now(timezone.utc),
            failed=error is not None,
            error=error,
        )
        dbsession.add(update)
        dbsession.commit()
