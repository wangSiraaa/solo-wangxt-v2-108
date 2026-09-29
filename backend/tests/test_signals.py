import numpy as np

from app.signals import (
    INTERPOLATED,
    MEASURED,
    MISSING,
    build_display_series,
    detect_gaps,
    moving_average_temp,
    windowed_ror,
)


def test_windowed_ror_known_slope():
    """线性升温 12°C/min，末端窗口回归应恢复该斜率。"""
    t = np.arange(0, 120, 2.0)
    y = 20.0 + 12.0 / 60.0 * t  # 0.2 °C/s
    ror = windowed_ror(t, y, window_s=30, min_anchors=4)
    valid = ror[~np.isnan(ror)]
    assert valid.size > 50
    assert np.all(np.abs(valid - 12.0) < 1e-6)


def test_ror_window_semantics_and_gap_restart():
    """缺口后复出的点 RoR 必须为空，不能用缺口两侧点算出穿越式温升率。"""
    t = np.arange(0, 200, 2.0)
    y = 100.0 + 0.1 * t
    keep = ~((t > 80) & (t < 130))  # 50s 失联
    t2, y2 = t[keep], y[keep]
    ror = windowed_ror(t2, y2, window_s=30, min_anchors=4)
    first_after = np.where(t2 >= 130)[0][0]
    # 复出后一个窗口长度内，锚点都不足，应为 NaN
    assert np.isnan(ror[first_after])
    assert np.isnan(ror[first_after + 5])
    # 恢复足够锚点后重新有数
    later = np.where(t2 >= 130 + 30)[0][0]
    assert not np.isnan(ror[later])


def test_detect_gaps_uneven_axis():
    t = np.array([0, 2, 4, 6, 30, 32, 34], dtype=float)
    gaps = detect_gaps(t)
    assert len(gaps) == 1
    assert gaps[0].start_t == 6 and gaps[0].end_t == 30
    assert gaps[0].n_measured_skipped >= 10


def test_short_gap_interpolated_long_gap_missing():
    t = np.concatenate([np.arange(0, 100, 2.0), np.arange(110, 200, 2.0)])
    y = np.full_like(t, 100.0)
    origins = [MEASURED] * t.size
    # 10s 短缺口：插值（默认阈值 15s）
    tt, vv, oo, gaps = build_display_series(t, y, origins, gap_threshold_s=15)
    assert any(g.filled for g in gaps)
    assert (oo == INTERPOLATED).sum() >= 3
    assert not np.any((oo == INTERPOLATED) & np.isnan(vv))

    # 同一缺口，阈值等于缺口时长 10s：严格小于才插值，故必须留空
    tt2, vv2, oo2, gaps2 = build_display_series(t, y, origins, gap_threshold_s=10)
    assert not any(g.filled for g in gaps2)
    assert (oo2 == MISSING).sum() >= 1
    assert np.isnan(vv2[oo2 == MISSING]).all()
    # 阈值 0 = 一律不插值
    tt3, vv3, oo3, gaps3 = build_display_series(t, y, origins, gap_threshold_s=0)
    assert not any(g.filled for g in gaps3)
    # 所有插值点必须显式标注，绝不出现未标注的非实测点
    assert set(np.unique(oo2)) <= {MEASURED, MISSING}


def test_smoothing_does_not_mutate_input():
    """改变平滑参数只影响平滑副本，输入数组逐位不变。"""
    rng = np.random.default_rng(0)
    t = np.arange(0, 300, 2.0)
    y = 100 + 0.15 * t + rng.normal(0, 0.5, t.size)
    y_copy = y.copy()
    _ = moving_average_temp(y, 8.0, t)
    _ = moving_average_temp(y, 30.0, t)
    _ = windowed_ror(t, y, window_s=15)
    _ = windowed_ror(t, y, window_s=60)
    assert np.array_equal(y, y_copy)
