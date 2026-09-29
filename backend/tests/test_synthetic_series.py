import numpy as np

from app.signals import INTERPOLATED, MISSING
from app.models import Batch
from app.services import build_series_payload
from app.synthetic import seed_if_empty


def test_seed_creates_two_batches_with_gaps_and_noise(seeded):
    batches = seeded.query(Batch).order_by(Batch.id).all()
    assert len(batches) == 2
    for b in batches:
        assert len(b.samples) > 200
        bts = np.array([s.bean_temp_c for s in sorted(b.samples, key=lambda s: s.t_s)])
        assert np.std(np.diff(bts)) > 0.1
        payload = build_series_payload(b)
        assert len(payload["gaps"]) >= 2


def test_short_and_long_gap_origin_labels(seeded):
    b = seeded.query(Batch).filter(Batch.code.like("%02")).one()
    payload = build_series_payload(b)
    origins = {p["origin"] for p in payload["display_bean"]}
    # 同时存在短缺口插值与长缺口留空
    assert INTERPOLATED in origins and MISSING in origins
    missing = [p for p in payload["display_bean"] if p["origin"] == MISSING]
    assert all(p["v"] is None for p in missing)
    interp = [p for p in payload["display_bean"] if p["origin"] == INTERPOLATED]
    assert all(p["v"] is not None for p in interp)


def test_raw_samples_identical_regardless_of_window(seeded):
    """核心约束：改 RoR 窗口/插值阈值，原始温度一行都不能变。"""
    b = seeded.query(Batch).first()
    p1 = build_series_payload(b, ror_window_s=15, max_interp_gap_s=5)
    p2 = build_series_payload(b, ror_window_s=60, max_interp_gap_s=30)
    assert p1["raw_samples"] == p2["raw_samples"]
    before = [(s.t_s, s.bean_temp_c, s.env_temp_c, s.quality) for s in b.samples]
    _ = build_series_payload(b, ror_window_s=5, max_interp_gap_s=0)
    after = [(s.t_s, s.bean_temp_c, s.env_temp_c, s.quality) for s in b.samples]
    assert before == after
    r1 = [x["bean_ror_c_per_min"] for x in p1["ror"]]
    r2 = [x["bean_ror_c_per_min"] for x in p2["ror"]]
    assert r1 != r2
    assert p1["ror_method"]["window_s"] == 15
    assert p2["ror_method"]["window_s"] == 60


def test_spikes_preserved_as_raw(seeded):
    b = seeded.query(Batch).filter(Batch.code == "A-20260927-01").one()
    assert any(s.quality == "spike" for s in b.samples)
    payload = build_series_payload(b)
    assert any(x["quality"] == "spike" for x in payload["raw_samples"])
