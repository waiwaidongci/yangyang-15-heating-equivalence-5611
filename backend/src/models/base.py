from datetime import datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from src.config.runtime import DSN


class Base(DeclarativeBase):
    pass


def utc_now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


engine = create_engine(DSN, pool_pre_ping=True)
Session = sessionmaker(engine, expire_on_commit=False)
