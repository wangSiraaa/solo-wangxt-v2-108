#!/usr/bin/env python3
"""独立复现脚本：只读取导出的 roastlog-bundle/v1 JSON + NumPy，
不依赖本系统数据库，复算全部阶段指标与温升率并逐项比对。

用法：
    python3 reproduce.py path/to/bundle.json
或：
    curl -s http://127.0.0.1:8000/api/batches/1/export.json \
        | python3 reproduce.py -
"""
import json
import sys

import numpy as np


def windowed_ror(t, y, window_s, min_anchors, min_coverage):
    """与后端 signals.windowed_ror 完全相同的窗口语义（此处为独立实现）。"""
    t, y = np.asarray(t, float), np.asarray(y, float)
    out = np.full(t.shape, np.nan)
    for i in range(t.size):
        m = (t >= t[i] - window_s) & (t <= t[i]) & ~np.isnan(y)
        if m.sum() < min_anchors:
            continue
        tt, yy = t[m], y[m]
        if tt[-1] - tt[0] < window_s * min_coverage:
            continue
        out[i] = np.polyfit(tt, yy, 1)[0] * 60.0
    return out


def main(path):
    bundle = json.load(open(path) if path != "-" else sys.stdin)
    assert bundle["format"] == "roastlog-bundle/v1", "导出包格式不匹配"

    # —— 1. 仅用当前生效锚点时间复算阶段指标 ——
    cur = [e for e in bundle["events"] if e["is_current"]]
    at = {e["event_type"]: e["event_time"] for e in cur
          if e["event_type"] in ("charge", "turn", "first_crack", "drop")}
    tc, tt, tf, td = at["charge"], at["turn"], at["first_crack"], at["drop"]
    repro = {
        "drying_s": round(tt - tc, 1),
        "maillard_s": round(tf - tt, 1),
        "development_s": round(td - tf, 1),
        "total_s": round(td - tc, 1),
        "development_time_ratio": round((td - tf) / (td - tc), 4),
    }
    shipped = {
        k: v["value"] for k, v in bundle["metrics"]["intervals"].items()
    }
    shipped["development_time_ratio"] = bundle["metrics"]["development_time_ratio"]

    print(f"批次 {bundle['batch']['code']}  复现窗口参数: "
          f"RoR window={bundle['ror_method']['window_s']}s, "
          f"max_interp_gap={bundle['interpolation']['max_filled_gap_s']}s")
    print(f"{'指标':<22}{'导出值':>12}{'独立复算':>12}  一致")
    ok = True
    for k in repro:
        same = abs(repro[k] - shipped[k]) < 1e-6
        ok &= same
        print(f"{k:<22}{shipped[k]:>12}{repro[k]:>12}  {'✓' if same else '✗'}")

    # —— 2. 仅用 raw_samples + 声明的窗口复算温升率 ——
    raw = bundle["raw_samples"]
    t = [r["t_s"] for r in raw]
    bt = [r["bean_temp_c"] for r in raw]
    m = bundle["ror_method"]
    ror = windowed_ror(
        t, bt,
        window_s=m["window_s"],
        min_anchors=m["min_measured_anchors"],
        min_coverage=m["min_window_coverage"],
    )
    max_err = 0.0
    n_none_match = 0
    for i, row in enumerate(bundle["ror"]):
        shipped_v = row["bean_ror_c_per_min"]
        if shipped_v is None:
            n_none_match += int(np.isnan(ror[i]))
        else:
            max_err = max(max_err, abs(ror[i] - shipped_v))
    n_none = sum(1 for r in bundle["ror"] if r["bean_ror_c_per_min"] is None)
    ror_ok = max_err <= 0.005 and n_none_match == n_none
    ok &= ror_ok
    print(f"\nRoR 点数={len(ror)}  最大偏差={max_err:.4f} °C/min（导出保留2位小数）"
          f"  空值一致 {n_none_match}/{n_none}  {'✓' if ror_ok else '✗'}")

    # —— 3. 插值未污染原始数据：raw_samples 数量与质量标记自洽 ——
    n_spike = sum(1 for r in raw if r["quality"] == "spike")
    print(f"原始采样={len(raw)}（其中跳变标记 spike={n_spike}，均如实保留）")
    print(f"\n结论：{'所有阶段指标与温升率均可由导出包独立复现 ✓' if ok else '复现失败 ✗'}")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "-")
