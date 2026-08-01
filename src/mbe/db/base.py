from __future__ import annotations

import os
from typing import Iterator

from sqlalchemy import MetaData, create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import NullPool

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


def database_url(required: bool = False) -> str | None:
    value = os.environ.get("MBE_DATABASE_URL")
    if required and not value:
        raise RuntimeError("MBE_DATABASE_URL is required for this operation")
    return value


def create_database_engine(url: str | None = None) -> Engine:
    url = url or database_url(required=True)
    assert url is not None
    kwargs: dict = {"pool_pre_ping": True}
    if url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
    elif os.environ.get("MBE_DATABASE_POOL_MODE", "serverless") == "serverless":
        # A hosted transaction pooler (for example PgBouncer) owns pooling;
        # function instances should not accumulate their own idle connections.
        kwargs["poolclass"] = NullPool
        kwargs["connect_args"] = {"connect_timeout": 8}
    return create_engine(url, **kwargs)


def session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(engine, expire_on_commit=False)


def session_scope(engine: Engine) -> Iterator[Session]:
    session = session_factory(engine)()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
