from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import PlainTextResponse, Response
from sqlalchemy.orm import Session

from .config import settings
from .database import get_db
from .exporters import build_export_bundle, events_csv, samples_csv
from .metrics import compute_metrics, metrics_to_dict
from .models import Batch
from .schemas import EventIn
from .services import (
    apply_manual_event,
    batch_summary,
    build_series_payload,
    list_events,
)
from .synthetic import seed_if_empty

router = APIRouter(prefix="/api")


def _get_batch(db: Session, batch_id: int) -> Batch:
    b = db.get(Batch, batch_id)
    if b is None:
        raise HTTPException(404, f"批次 {batch_id} 不存在")
    return b


@router.post("/seed")
def seed(db: Session = Depends(get_db)):
    n = seed_if_empty(db)
    return {"seeded": n}


@router.get("/batches")
def list_batches(db: Session = Depends(get_db)):
    rows = db.query(Batch).order_by(Batch.id).all()
    return [batch_summary(b) for b in rows]


@router.get("/batches/{batch_id}")
def batch_detail(
    batch_id: int,
    ror_window_s: float | None = Query(None, gt=0, le=300),
    max_interp_gap_s: float | None = Query(None, ge=0, le=120),
    db: Session = Depends(get_db),
):
    b = _get_batch(db, batch_id)
    payload = build_series_payload(
        b,
        ror_window_s=ror_window_s if ror_window_s is not None else settings.default_ror_window_s,
        max_interp_gap_s=max_interp_gap_s if max_interp_gap_s is not None else settings.default_max_interp_gap_s,
    )
    return {
        "batch": batch_summary(b)
        | {
            "profile_name_full": b.profile_name,
            "description": b.description,
            "charge_g": b.charge_g,
            "target_drop_c": b.target_drop_c,
            "synth_seed": b.synth_seed,
        },
        **payload,
        "events": list_events(db, batch_id, include_history=True),
        "metrics": metrics_to_dict(compute_metrics(b)),
    }


@router.get("/batches/{batch_id}/events")
def get_events(batch_id: int, db: Session = Depends(get_db)):
    _get_batch(db, batch_id)
    return list_events(db, batch_id, include_history=True)


@router.post("/batches/{batch_id}/events", status_code=201)
def add_event(batch_id: int, body: EventIn, db: Session = Depends(get_db)):
    b = _get_batch(db, batch_id)
    if not body.operator.strip():
        raise HTTPException(422, "人工修正必须填写操作员（operator）以保留来源")
    ev = apply_manual_event(
        db, b,
        event_type=body.event_type,
        event_time=body.event_time,
        value=body.value,
        operator=body.operator,
        note=body.note,
    )
    return {"event": list_events(db, batch_id)}  # 返回全部历史便于前端刷新


def _one_event(db: Session, event_id: int):
    from .models import Event

    ev = db.get(Event, event_id)
    if ev is None:
        raise HTTPException(404, f"事件 {event_id} 不存在")
    return ev


@router.post("/events/{event_id}/accept-suggestion", status_code=201)
def accept_suggestion(
    event_id: int,
    operator: str = Query(...),
    note: str = "",
    db: Session = Depends(get_db),
):
    """把算法建议（如回温点检测器）确认成人工记录：旧锚点同样保留为历史。"""
    src = _one_event(db, event_id)
    b = _get_batch(db, src.batch_id)
    if not operator.strip():
        raise HTTPException(422, "确认建议必须填写操作员")
    ev = apply_manual_event(
        db, b,
        event_type=src.event_type,
        event_time=src.event_time,
        value=src.value,
        operator=operator,
        note=note or f"操作员确认算法建议（事件 #{src.id}）",
    )
    return {"event_id": ev.id, "events": list_events(db, b.id)}


@router.post("/events/{event_id}/revert", status_code=201)
def revert_event(event_id: int, operator: str = Query(...), db: Session = Depends(get_db)):
    """恢复被取代的历史记录：目标行重新 current，当前行失效并指向它。"""
    from .models import ANCHOR_EVENT_TYPES, Event

    target = _one_event(db, event_id)
    if target.event_type not in ANCHOR_EVENT_TYPES:
        raise HTTPException(422, "只有锚点事件支持恢复历史版本")
    current = (
        db.query(Event)
        .filter(
            Event.batch_id == target.batch_id,
            Event.event_type == target.event_type,
            Event.is_current.is_(True),
        )
        .one_or_none()
    )
    if not operator.strip():
        raise HTTPException(422, "恢复历史必须填写操作员")
    if current is not None and current.id != target.id:
        current.is_current = False
    target.is_current = True
    new_note = Event(
        batch_id=target.batch_id,
        event_type=target.event_type,
        event_time=target.event_time,
        value=target.value,
        source="manual",
        operator=operator.strip(),
        note=f"恢复到历史版本（事件 #{target.id}，原来源 {target.source}）",
        method={"action": "revert", "restored_event_id": target.id},
        is_current=False,
    )
    # 恢复操作本身也留痕，但不重复占用 current
    db.add(new_note)
    db.commit()
    return {"events": list_events(db, target.batch_id)}


@router.get("/compare")
def compare(
    a: int = Query(..., description="批次 A id"),
    b: int = Query(..., description="批次 B id"),
    ror_window_s: float | None = Query(None, gt=0, le=300),
    max_interp_gap_s: float | None = Query(None, ge=0, le=120),
    db: Session = Depends(get_db),
):
    ba, bb = _get_batch(db, a), _get_batch(db, b)
    win = settings.default_ror_window_s if ror_window_s is None else ror_window_s
    interp_max = (
        settings.default_max_interp_gap_s if max_interp_gap_s is None else max_interp_gap_s
    )
    pa = build_series_payload(ba, win, interp_max)
    pb = build_series_payload(bb, win, interp_max)
    return {
        "batches": [
            pa | batch_summary(ba)
            | {"metrics": metrics_to_dict(compute_metrics(ba))},
            pb | batch_summary(bb)
            | {"metrics": metrics_to_dict(compute_metrics(bb))},
        ],
        "disclaimer": (
            "两批次曲线按时间轴并置，仅用于观察风门调整前后的形态差异；"
            "批次间还存在豆量、环境、原料等差异，本视图不提供、也不暗示因果结论。"
        ),
        "ror_method": pa["ror_method"],
    }


@router.get("/batches/{batch_id}/export.json")
def export_json(
    batch_id: int,
    ror_window_s: float | None = Query(None, gt=0, le=300),
    max_interp_gap_s: float | None = Query(None, ge=0, le=120),
    db: Session = Depends(get_db),
):
    b = _get_batch(db, batch_id)
    bundle = build_export_bundle(
        b,
        ror_window_s if ror_window_s is not None else settings.default_ror_window_s,
        max_interp_gap_s if max_interp_gap_s is not None else settings.default_max_interp_gap_s,
    )
    import json

    return Response(
        json.dumps(bundle, ensure_ascii=False, indent=2, default=str),
        media_type="application/json",
        headers={
            "Content-Disposition": f'attachment; filename="{b.code}.bundle.json"'
        },
    )


@router.get("/batches/{batch_id}/export/{kind}.csv", response_class=PlainTextResponse)
def export_csv(batch_id: int, kind: str, db: Session = Depends(get_db)):
    b = _get_batch(db, batch_id)
    if kind == "samples":
        body, name = samples_csv(b), f"{b.code}.samples.csv"
    elif kind == "events":
        body, name = events_csv(b), f"{b.code}.events.csv"
    else:
        raise HTTPException(404, "csv 种类仅支持 samples / events")
    return PlainTextResponse(
        body,
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
        media_type="text/csv; charset=utf-8",
    )
