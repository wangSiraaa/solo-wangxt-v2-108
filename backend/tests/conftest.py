"""测试夹具：每个用例使用独立临时 SQLite（表结构与 PostgreSQL 一致，由 ORM 保证）。"""
import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import models  # noqa: E402
from app.database import Base  # noqa: E402


@pytest.fixture()
def db():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    s = sessionmaker(bind=engine, expire_on_commit=False)()
    yield s
    s.close()


@pytest.fixture()
def seeded(db):
    from app.synthetic import seed_if_empty

    seed_if_empty(db)
    return db
