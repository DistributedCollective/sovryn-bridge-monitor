from datetime import datetime, timezone
import logging
import os

from sqlalchemy import text
from sqlalchemy.orm import Session

from bridge_monitor.models.ledger_meta import LedgerUpdateMeta

SCRIPT_NAME = "create_ledger.sql"

logger = logging.getLogger(__name__)


def create_ledger(dbsession: Session):
    error = None
    try:
        ledger_script = text(
            open(os.path.join(os.path.dirname(__file__), SCRIPT_NAME)).read()
        )
        logger.info("running %s script", SCRIPT_NAME)
        dbsession.execute(ledger_script)
    except Exception as e:
        logger.error("error running %s script: %s", SCRIPT_NAME, e)
        error = str(e)
    finally:
        update = LedgerUpdateMeta(
            timestamp=datetime.now(timezone.utc),
            failed=error is not None,
            error=error,
        )
        dbsession.add(update)
        dbsession.commit()
