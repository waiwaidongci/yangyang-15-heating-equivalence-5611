import logging
import sys
import time

from sqlalchemy import text

from src.models.base import Session
from src.services.broker import redis
from src.services.delivery import dispatch_pending
from src.services.runs import run_pending

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
HEARTBEAT = 'desk:worker-alive'


def main():
    while True:
        try:
            with Session.begin() as db:
                ran = run_pending(db)
            with Session.begin() as db:
                dispatched = dispatch_pending(db)
            redis.set(HEARTBEAT, 'yes', ex=12)
            if not ran and not dispatched:
                redis.blpop('desk:wake', timeout=1)
        except Exception:
            logger.exception('Worker could not finish its cycle')
            time.sleep(2)


def health():
    with Session() as db:
        db.execute(text('SELECT 1'))
    return 0 if redis.get(HEARTBEAT) == 'yes' else 1


if __name__ == '__main__':
    if sys.argv[1:] == ['health']:
        sys.exit(health())
    main()
