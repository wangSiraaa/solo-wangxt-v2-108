"""导出：JSON 全量包（可离线复现所有阶段指标）+ 原始 CSV。

JSON 包包含复现所需的全部输入与参数：原始采样（含质量标记）、
完整事件历史（含失效记录与来源链）、RoR 窗口参数、插值阈值、指标结果。
"""
import csv
import io
import json

from .metrics import compute_metrics, metrics_to_dict
from .models import Batch
from .services import build_series_payload, event_to_dict


def build_export_bundle(batch: Batch, ror_window_s: float, max_interp_gap_s: float) -> dict:
    series = build_series_payload(
        batch,
        ror_window_s=ror_window_s,
        max_interp_gap_s=max_interp_gap_s,
    )
    metrics = metrics_to_dict(compute_metrics(batch))
    return {
        "format": "roastlog-bundle/v1",
        "batch": {
            "id": batch.id,
            "code": batch.code,
            "profile_name": batch.profile_name,
            "bean_origin": batch.bean_origin,
            "charge_g": batch.charge_g,
            "target_drop_c": batch.target_drop_c,
            "roast_date": batch.roast_date,
            "description": batch.description,
            "synth_seed": batch.synth_seed,
        },
        # 复现指标只需 raw_samples + current 事件，但完整历史一并导出
        "raw_samples": series["raw_samples"],
        "events": [event_to_dict(e) for e in sorted(
            batch.events, key=lambda x: (x.event_time, x.id)
        )],
        "ror_method": series["ror_method"],
        "interpolation": series["interpolation"],
        "gaps": series["gaps"],
        "turn_suggestion": series["turn_suggestion"],
        # 温升率与显示序列一并导出：用同一窗口参数即可由 raw_samples 复算
        "ror": series["ror"],
        "display_bean": series["display_bean"],
        "display_env": series["display_env"],
        "metrics": metrics,
        "disclaimers": [
            "raw_samples 为探针原始读数，quality=spike 表示已保留的跳变点",
            "插值段仅用于显示，不参与温升率计算与指标计算",
            "两批次风门前后的曲线差异为观察性并置，不构成因果结论",
        ],
    }


def samples_csv(batch: Batch) -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["t_s", "bean_temp_c", "env_temp_c", "quality"])
    for s in sorted(batch.samples, key=lambda x: x.t_s):
        w.writerow([f"{s.t_s:.2f}", f"{s.bean_temp_c:.1f}", f"{s.env_temp_c:.1f}", s.quality])
    return buf.getvalue()


def events_csv(batch: Batch) -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow([
        "id", "event_type", "event_time_s", "value", "source",
        "operator", "note", "method", "supersedes_id", "is_current", "created_at",
    ])
    for e in sorted(batch.events, key=lambda x: (x.event_time, x.id)):
        w.writerow([
            e.id, e.event_type, f"{e.event_time:.2f}",
            "" if e.value is None else e.value,
            e.source, e.operator, e.note,
            "" if e.method is None else json.dumps(e.method, ensure_ascii=False),
            "" if e.supersedes_id is None else e.supersedes_id,
            e.is_current, e.created_at.isoformat(),
        ])
    return buf.getvalue()
