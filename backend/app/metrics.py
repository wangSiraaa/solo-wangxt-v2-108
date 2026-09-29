"""阶段指标：全部按**明确的时间区间**计算，不用成品评分替代过程记录。

时间零点 = 下豆（charge）。区间定义：
- 干燥区间   [charge, turn]          （下豆 -> 回温点）
- 梅纳区间   [turn, first_crack]     （回温点 -> 一爆开始）
- 发展区间   [first_crack, drop]     （一爆 -> 出锅）
- 总烘焙时长 [charge, drop]
- 发展时间比 DTR = (drop - first_crack) / (drop - charge)
  （分母为完整烘焙时长，这是本系统明确采用的定义）

温度取最近实测点的读数（不做插值），并注明该读数时间；
任一锚点缺失或顺序非法时，对应指标返回 None 并在 errors 中说明。
"""
from dataclasses import dataclass, field

import numpy as np

from .models import ANCHOR_EVENT_TYPES, Batch, Event


@dataclass
class Anchor:
    event_type: str
    t_s: float
    temp_c: float | None
    temp_t_s: float | None
    event_id: int
    source: str
    operator: str
    note: str


@dataclass
class PhaseMetrics:
    intervals: dict = field(default_factory=dict)
    development_time_ratio: float | None = None
    anchors: dict = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)


def current_anchors(events: list[Event]) -> dict[str, Event]:
    out: dict[str, Event] = {}
    for e in events:
        if e.event_type in ANCHOR_EVENT_TYPES and e.is_current:
            # 理论上同类型只有一条 current；防御性取时间最新记录
            if e.event_type not in out or e.id > out[e.event_type].id:
                out[e.event_type] = e
    return out


def compute_metrics(batch: Batch) -> PhaseMetrics:
    m = PhaseMetrics()
    times = sorted(s.t_s for s in batch.samples)
    by_t = {round(s.t_s, 2): s for s in batch.samples}

    def temp_at(t):
        # 从完整采样集中取时间最近的点（times 已排序）
        if not times:
            return None, None
        i = int(np.argmin(np.abs(np.asarray(times) - t)))
        s = by_t[round(times[i], 2)]
        return s.bean_temp_c, round(s.t_s, 2)

    anchors = current_anchors(list(batch.events))
    for etype, e in anchors.items():
        tc, tt = temp_at(e.event_time)
        m.anchors[etype] = Anchor(
            event_type=etype,
            t_s=round(e.event_time, 2),
            temp_c=tc,
            temp_t_s=tt,
            event_id=e.id,
            source=e.source,
            operator=e.operator,
            note=e.note,
        )

    required = ["charge", "turn", "first_crack", "drop"]
    missing = [k for k in required if k not in m.anchors]
    if missing:
        m.errors.append(
            "缺少锚点事件，无法计算完整阶段指标：" + ", ".join(missing)
        )
        return m

    t = {k: m.anchors[k].t_s for k in required}
    if not (t["charge"] <= t["turn"] <= t["first_crack"] <= t["drop"]):
        m.errors.append(
            "锚点时间顺序非法（要求 下豆 <= 回温点 <= 一爆 <= 出锅），"
            "请在事件面板修正"
        )
        return m

    drying = t["turn"] - t["charge"]
    maillard = t["first_crack"] - t["turn"]
    development = t["drop"] - t["first_crack"]
    total = t["drop"] - t["charge"]

    m.intervals = {
        "drying_s": {
            "value": round(drying, 1),
            "label": "干燥区间 [下豆→回温点]",
            "start_event": "charge",
            "end_event": "turn",
        },
        "maillard_s": {
            "value": round(maillard, 1),
            "label": "梅纳区间 [回温点→一爆]",
            "start_event": "turn",
            "end_event": "first_crack",
        },
        "development_s": {
            "value": round(development, 1),
            "label": "发展区间 [一爆→出锅]",
            "start_event": "first_crack",
            "end_event": "drop",
        },
        "total_s": {
            "value": round(total, 1),
            "label": "总烘焙时长 [下豆→出锅]",
            "start_event": "charge",
            "end_event": "drop",
        },
    }
    m.development_time_ratio = (
        round(development / total, 4) if total > 0 else None
    )
    return m


def metrics_to_dict(m: PhaseMetrics) -> dict:
    return {
        "development_time_ratio": m.development_time_ratio,
        "development_time_ratio_definition": (
            "(出锅时间 - 一爆时间) / (出锅时间 - 下豆时间)，"
            "时间零点为下豆，分母为完整烘焙时长"
        ),
        "intervals": m.intervals,
        "anchors": {
            k: {
                "event_type": a.event_type,
                "t_s": a.t_s,
                "bean_temp_c": a.temp_c,
                "temp_sample_t_s": a.temp_t_s,
                "event_id": a.event_id,
                "source": a.source,
                "operator": a.operator,
                "note": a.note,
            }
            for k, a in m.anchors.items()
        },
        "errors": m.errors,
    }
