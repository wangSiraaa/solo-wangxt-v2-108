"""端到端 API 测试（FastAPI TestClient + 临时 SQLite）。"""
import os
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app.main as main_mod  # noqa: E402
from app import database as db_mod  # noqa: E402
from app.database import Base  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture()
def client(monkeypatch):
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine, expire_on_commit=False)
    monkeypatch.setattr(db_mod, "engine", engine)
    monkeypatch.setattr(db_mod, "SessionLocal", TestSession)
    # lifespan 启动钩子改用测试引擎（不在磁盘建库）
    monkeypatch.setattr(main_mod, "init_db", lambda: None)
    monkeypatch.setattr(main_mod, "SessionLocal", TestSession)

    from app.synthetic import seed_if_empty

    s = TestSession()
    seed_if_empty(s)
    s.close()

    with TestClient(app) as c:
        yield c


def test_health_and_list(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["ror_default_window_s"] == 30
    r = client.get("/api/batches")
    assert len(r.json()) == 2


def test_detail_declares_window_and_origins(client):
    bid = client.get("/api/batches").json()[0]["id"]
    r = client.get(f"/api/batches/{bid}?ror_window_s=20&max_interp_gap_s=10")
    d = r.json()
    assert d["ror_method"]["window_s"] == 20
    assert d["ror_method"]["estimator"] == "trailing_window_least_squares"
    assert "interpolated" in d["interpolation"]["origins"]
    # 改变参数重取：原始采样不变
    r2 = client.get(f"/api/batches/{bid}?ror_window_s=45&max_interp_gap_s=30")
    assert r2.json()["raw_samples"] == d["raw_samples"]


def test_manual_correction_flow(client):
    bid = client.get("/api/batches").json()[0]["id"]
    evts = client.get(f"/api/batches/{bid}/events").json()
    turn_old = [e for e in evts if e["event_type"] == "turn" and e["is_current"]][0]

    # 缺少操作员应被拒绝（来源必须保留）
    r = client.post(f"/api/batches/{bid}/events", json={
        "event_type": "turn", "event_time": 83, "operator": " ", "note": "x"})
    assert r.status_code == 422

    r = client.post(f"/api/batches/{bid}/events", json={
        "event_type": "turn", "event_time": 83, "value": 97.5,
        "operator": "李烘焙", "note": "听音确认回温偏晚"})
    assert r.status_code == 201
    evts2 = r.json()["event"]
    turns = [e for e in evts2 if e["event_type"] == "turn"]
    current = [e for e in turns if e["is_current"]]
    assert len(current) == 1
    assert current[0]["event_time"] == 83
    assert current[0]["operator"] == "李烘焙"
    old = [e for e in turns if e["id"] == turn_old["id"]][0]
    assert old["is_current"] is False
    assert current[0]["supersedes_id"] == turn_old["id"]

    # 指标随修正更新
    detail = client.get(f"/api/batches/{bid}").json()
    assert detail["metrics"]["intervals"]["drying_s"]["value"] == 83


def test_damper_and_marker_events_append(client):
    bid = client.get("/api/batches").json()[0]["id"]
    r = client.post(f"/api/batches/{bid}/events", json={
        "event_type": "damper", "event_time": 260, "value": 40,
        "operator": "李烘焙", "note": "一爆前再收风门"})
    assert r.status_code == 201
    dampers = [e for e in r.json()["event"]
               if e["event_type"] == "damper" and e["is_current"]]
    assert len(dampers) == 3  # 2 条预置 + 1 条追加，且不互相取代


def test_compare_disclaimer(client):
    ids = [b["id"] for b in client.get("/api/batches").json()]
    r = client.get(f"/api/compare?a={ids[0]}&b={ids[1]}")
    d = r.json()
    assert len(d["batches"]) == 2
    assert "因果" in d["disclaimer"]
    assert d["ror_method"]["window_s"] == 30


def test_export_endpoints(client):
    bid = client.get("/api/batches").json()[0]["id"]
    rj = client.get(f"/api/batches/{bid}/export.json")
    assert rj.status_code == 200
    bundle = rj.json()
    assert bundle["format"] == "roastlog-bundle/v1"
    assert bundle["metrics"]["development_time_ratio"] is not None

    rc = client.get(f"/api/batches/{bid}/export/samples.csv")
    assert rc.status_code == 200
    assert rc.text.splitlines()[0] == "t_s,bean_temp_c,env_temp_c,quality"
    re_ = client.get(f"/api/batches/{bid}/export/events.csv")
    assert "event_type" in re_.text.splitlines()[0]
