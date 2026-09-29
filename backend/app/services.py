"""数据装配：把原始采样加工为 API 所需序列，加工结果与原始数据严格分离。"""
import numpy as np
from sqlalchemy.orm import Session

from .config import settings
from .models import ANCHOR_EVENT_TYPES, Batch, Event
from .signals import (
    INTERPOLATED,
    MEASURED,
    MISSING,
    build_display_series,
    detect_gaps,
    detect_turn,
    windowed_ror,
)


def _samples_arrays(batch: Batch):
    rows = sorted(batch.samples, key=lambda s: s.t_s)
    t = np.array([r.t_s for r in rows], dtype=float)
    bt = np.array([r.bean_temp_c for r in rows], dtype=float)
    et = np.array([r.env_temp_c for r in rows], dtype=float)
    q = [r.quality for r in rows]
    return t, bt, et, q, rows


def batch_summary(b: Batch) -> dict:
    t, *_ = _samples_arrays(b)
    gaps = detect_gaps(t) if t.size >= 3 else []
    return {
        "id": b.id,
        "code": b.code,
        "profile_name": b.profile_name,
        "bean_origin": b.bean_origin,
        "roast_date": b.roast_date,
        "n_samples": len(b.samples),
        "n_gaps": len(gaps),
    }


def build_series_payload(
    batch: Batch,
    ror_window_s: float | None = None,
    max_interp_gap_s: float | None = None,
) -> dict:
    """返回绘图/分析所需全部序列。

    raw_* 与数据库行逐行对应；display_* 含插值/缺测标记且单独成键；
    ror 仅在实测点上计算并随响应回传窗口参数（"温升率采用的窗口"）。
    """
    win = settings.default_ror_window_s if ror_window_s is None else ror_window_s
    interp_max = (
        settings.default_max_interp_gap_s
        if max_interp_gap_s is None
        else max_interp_gap_s
    )

    t, bt, et, quality, rows = _samples_arrays(batch)

    # —— 温升率：只用实测点，末端线性回归窗口 ——
    ror_bt = windowed_ror(
        t, bt,
        window_s=win,
        min_anchors=settings.ror_min_anchors,
        min_coverage=settings.ror_min_coverage,
    )
    ror_et = windowed_ror(
        t, et,
        window_s=win,
        min_anchors=settings.ror_min_anchors,
        min_coverage=settings.ror_min_coverage,
    )

    # —— 显示序列：短缺口插值补线，长缺口 NaN 断线 ——
    origins = [MEASURED] * t.size
    dbt_t, dbt_v, dbt_o, gaps_bt = build_display_series(
        t, bt, origins, gap_threshold_s=interp_max
    )
    det_t, det_v, det_o, _ = build_display_series(
        t, et, origins, gap_threshold_s=interp_max
    )

    def _disp(tt, vv, oo):
        return [
            {
                "t_s": round(float(x), 2),
                "v": None if np.isnan(y) else round(float(y), 2),
                "origin": str(o),
            }
            for x, y, o in zip(tt, vv, oo)
        ]

    suggestion = detect_turn(t, bt)

    return {
        "batch_id": batch.id,
        "code": batch.code,
        "raw_samples": [
            {
                "t_s": round(float(r.t_s), 2),
                "bean_temp_c": round(float(b), 1),
                "env_temp_c": round(float(e), 1),
                "quality": qq,
            }
            for r, b, e, qq in zip(rows, bt, et, quality)
        ],
        "display_bean": _disp(dbt_t, dbt_v, dbt_o),
        "display_env": _disp(det_t, det_v, det_o),
        "ror": [
            {
                "t_s": round(float(tt_), 2),
                "bean_ror_c_per_min": None
                if np.isnan(rb)
                else round(float(rb), 2),
                "env_ror_c_per_min": None
                if np.isnan(re_)
                else round(float(re_), 2),
            }
            for tt_, rb, re_ in zip(t, ror_bt, ror_et)
        ],
        "ror_method": {
            "estimator": "trailing_window_least_squares",
            "window_s": win,
            "min_measured_anchors": settings.ror_min_anchors,
            "min_window_coverage": settings.ror_min_coverage,
            "unit": "c_per_min",
            "note": (
                "末端窗口 [t-window, t] 内对实测点做最小二乘直线拟合取斜率；"
                "插值点不参与拟合；锚点不足（含失联后复出首点）时温升率为空"
            ),
        },
        "interpolation": {
            "max_filled_gap_s": interp_max,
            "origins": {
                MEASURED: "原始实测点",
                INTERPOLATED: "线性插值补线，非实测",
                MISSING: "探针失联超过阈值，留空断线",
            },
        },
        "gaps": [
            {
                "start_t_s": round(g.start_t, 2),
                "end_t_s": round(g.end_t, 2),
                "duration_s": round(g.duration_s, 2),
                "filled": g.filled,
                "n_measured_skipped": g.n_measured_skipped,
            }
            for g in gaps_bt
        ],
        "turn_suggestion": None
        if suggestion is None
        else {
            "t_s": round(suggestion.t_s, 2),
            "bean_temp_c": round(suggestion.bean_temp_c, 1),
            "method": suggestion.method,
        },
    }


def event_to_dict(e: Event) -> dict:
    return {
        "id": e.id,
        "event_type": e.event_type,
        "event_time": round(e.event_time, 2),
        "value": e.value,
        "source": e.source,
        "operator": e.operator,
        "note": e.note,
        "method": e.method,
        "supersedes_id": e.supersedes_id,
        "is_current": e.is_current,
        "created_at": e.created_at,
    }


def apply_manual_event(
    db: Session,
    batch: Batch,
    *,
    event_type: str,
    event_time: float,
    value: float | None,
    operator: str,
    note: str,
) -> Event:
    """人工修正：锚点事件旧记录失效但保留（supersedes 链）；过程事件追加。"""
    new = Event(
        batch_id=batch.id,
        event_type=event_type,
        event_time=float(event_time),
        value=value,
        source="manual",
        operator=operator.strip() or "unknown",
        note=note,
        method={"action": "manual_entry"},
        is_current=True,
    )

    if event_type in ANCHOR_EVENT_TYPES:
        previous = (
            db.query(Event)
            .filter(
                Event.batch_id == batch.id,
                Event.event_type == event_type,
                Event.is_current.is_(True),
            )
            .one_or_none()
        )
        if previous is not None:
            previous.is_current = False
            new.supersedes_id = previous.id
            new.method["action"] = "manual_correction"
            new.method["previous_time_s"] = previous.event_time
            new.method["previous_source"] = previous.source

    # 通过关系集合追加，保证同会话内 batch.events 立即可见
    batch.events.append(new)
    db.commit()
    db.refresh(new)
    return new


def list_events(db: Session, batch_id: int, include_history: bool = True):
    q = db.query(Event).filter(Event.batch_id == batch_id)
    if not include_history:
        q = q.filter(Event.is_current.is_(True))
    return [event_to_dict(e) for e in q.order_by(Event.event_time, Event.id).all()]
