from app.exporters import build_export_bundle
from app.metrics import compute_metrics, current_anchors, metrics_to_dict
from app.models import Batch, Event
from app.services import apply_manual_event
from app.signals import detect_turn


def test_metrics_intervals_and_dtr(seeded):
    b = seeded.query(Batch).filter(Batch.code == "A-20260927-01").one()
    m = compute_metrics(b)
    assert m.errors == []
    iv = m.intervals
    assert iv["drying_s"]["value"] == 78.0
    assert iv["maillard_s"]["value"] == 492.0
    assert iv["development_s"]["value"] == 120.0
    assert iv["total_s"]["value"] == 690.0
    # DTR = (690-570)/(690-0)，接口值四舍五入到 4 位小数
    assert abs(m.development_time_ratio - round(120 / 690, 4)) < 1e-12
    d = metrics_to_dict(m)
    assert "出锅时间" in d["development_time_ratio_definition"]


def test_manual_correction_keeps_provenance(seeded):
    b = seeded.query(Batch).filter(Batch.code == "A-20260927-01").one()
    old = current_anchors(list(b.events))["turn"]
    old_id = old.id
    assert old.source == "auto"

    ev = apply_manual_event(
        seeded, b,
        event_type="turn", event_time=82.0, value=97.0,
        operator="张师傅", note="听到回温反应偏晚",
    )
    assert ev.source == "manual" and ev.supersedes_id == old_id
    old = seeded.get(Event, old_id)
    assert old.is_current is False
    assert ev.method["previous_source"] == "auto"

    cur = current_anchors(list(b.events))["turn"]
    assert cur.id == ev.id
    # 修正后指标按新区间重算：干燥 82s，梅纳 488s，DTR 不变
    m = compute_metrics(b)
    assert m.intervals["drying_s"]["value"] == 82.0
    assert m.intervals["maillard_s"]["value"] == 488.0
    # 锚点带来源
    d = metrics_to_dict(m)
    assert d["anchors"]["turn"]["operator"] == "张师傅"
    assert d["anchors"]["turn"]["source"] == "manual"


def test_invalid_anchor_order_reported(seeded):
    b = seeded.query(Batch).filter(Batch.code == "A-20260927-01").one()
    apply_manual_event(
        seeded, b, event_type="drop", event_time=10.0, value=200.0,
        operator="测试", note="错误出锅时间",
    )
    m = compute_metrics(b)
    assert m.development_time_ratio is None
    assert any("顺序非法" in e for e in m.errors)


def test_missing_anchor_reported(db):
    from app.synthetic import SynthSpec, generate_batch

    spec = SynthSpec(
        code="X", profile_name="x", bean_origin="x", charge_g=1,
        target_drop_c=200, roast_date="2026-09-28", description="",
        bt_points=[(0, 100), (10, 120)],
        et_points=[(0, 110), (10, 130)],
        gaps=[], spikes=[],
        anchors=[("charge", 0, 100, "")],
        dampers=[],
    )
    b = generate_batch(db, spec, seed=1)
    m = compute_metrics(b)
    assert m.development_time_ratio is None
    assert any("缺少锚点" in e for e in m.errors)


def test_turn_detector_on_synthetic(seeded):
    b = seeded.query(Batch).filter(Batch.code == "A-20260927-01").one()
    rows = sorted(b.samples, key=lambda s: s.t_s)
    t = [s.t_s for s in rows]
    bt = [s.bean_temp_c for s in rows]
    sug = detect_turn(t, bt)
    assert sug is not None
    # 真实回温点 78s；噪声下检测器应落在 ±25s 内（且必须标注为算法建议）
    assert abs(sug.t_s - 78) <= 25
    assert sug.method["detector"] == "smoothed_minimum"


def test_export_bundle_reproduces_metrics(seeded):
    import numpy as np

    from app.signals import windowed_ror

    b = seeded.query(Batch).filter(Batch.code == "A-20260927-01").one()
    win = 30
    bundle = build_export_bundle(b, ror_window_s=win, max_interp_gap_s=15)

    # 1) 阶段指标可仅凭导出包中的锚点时间复算
    a = bundle["metrics"]["anchors"]
    tc, tt, tf, td = (a[k]["t_s"] for k in ("charge", "turn", "first_crack", "drop"))
    dtr = (td - tf) / (td - tc)
    assert abs(dtr - bundle["metrics"]["development_time_ratio"]) < 1e-4
    assert bundle["metrics"]["intervals"]["drying_s"]["value"] == tt - tc
    assert bundle["metrics"]["intervals"]["maillard_s"]["value"] == tf - tt
    assert bundle["metrics"]["intervals"]["development_s"]["value"] == td - tf

    # 2) RoR 可仅凭 raw_samples + 声明的窗口参数复算，逐点一致
    raw = bundle["raw_samples"]
    t = np.array([r["t_s"] for r in raw])
    bt = np.array([r["bean_temp_c"] for r in raw])
    ror = windowed_ror(t, bt, window_s=win, min_anchors=4, min_coverage=0.5)
    for i, row in enumerate(bundle["ror"]):
        if row["bean_ror_c_per_min"] is None:
            assert np.isnan(ror[i])
        else:
            assert abs(ror[i] - row["bean_ror_c_per_min"]) <= 0.005  # 导出保留 2 位小数
    assert bundle["ror_method"]["window_s"] == win

    # 3) 完整事件历史（含失效行与来源链）都在包里
    assert any(e["event_type"] == "turn" and e["is_current"] for e in bundle["events"])
    assert bundle["raw_samples"]  # 原始采样完整
