"""合成烘焙数据生成。

**不连接真实烘焙机**：所有曲线由 NumPy 合成，刻意包含
- 非均匀采样（基线 2s + 随机抖动）
- 探针短暂失联（整段采样缺失，需从时间轴推断）
- 个别跳变读数（quality=spike，如实保留不静默清洗）
- 测量噪声（白噪声 + 缓慢漂移）

每个批次的控制参数随对象写库，可复现同一合成曲线。
"""
from dataclasses import dataclass, field

import numpy as np

from .models import Batch, Event, Sample


@dataclass
class SynthSpec:
    code: str
    profile_name: str
    bean_origin: str
    charge_g: float
    target_drop_c: float
    roast_date: str
    description: str
    # 豆温控制折线 [(t_s, °C)]，PCHIP 式单调分段 + 段内弯折
    bt_points: list[tuple[float, float]]
    et_points: list[tuple[float, float]]
    # 失联缺口 [(start_s, end_s)]：区间内不产生任何采样行
    gaps: list[tuple[float, float]]
    # 跳变读数 (t_s, bean 增量, env 增量)
    spikes: list[tuple[float, float, float]]
    # 种子事件（下豆/回温/一爆/出锅），source=auto 表示合成预置
    anchors: list[tuple[str, float, float | None, str]]
    # 风门变化 (t_s, 风门档位 0-100)
    dampers: list[tuple[float, float]]
    markers: list[tuple[float, str]] = field(default_factory=list)
    noise_bt: float = 0.55
    noise_et: float = 0.85
    sample_base_s: float = 2.0


def _pchip_like_grid(points, t):
    """以控制折线为骨架：区间内用余弦缓动插值，保证整体光滑但不过冲。"""
    pts = np.asarray(points, dtype=float)
    tt, yy = pts[:, 0], pts[:, 1]
    out = np.interp(t, tt, yy)
    # 区间内用 smoothstep 缓动替换线性，模拟曲线形（不改变端点）
    for i in range(len(tt) - 1):
        m = (t >= tt[i]) & (t < tt[i + 1])
        if not m.any():
            continue
        u = np.clip((t[m] - tt[i]) / (tt[i + 1] - tt[i]), 0, 1)
        s = u * u * (3 - 2 * u)
        out[m] = yy[i] + (yy[i + 1] - yy[i]) * s
    return out


def _specs() -> list[SynthSpec]:
    # —— 批次 A：常规节奏，风门 65->55 在回温后；缺口两段均为短失联 ——
    a = SynthSpec(
        code="A-20260927-01",
        profile_name="日晒耶加雪菲·中度",
        bean_origin="埃塞俄比亚 耶加雪菲",
        charge_g=1200.0,
        target_drop_c=205.0,
        roast_date="2026-09-27",
        description="基准批次：风门在回温后由 65 调至 55。",
        bt_points=[
            (0, 185), (20, 112), (78, 96), (120, 118), (240, 150),
            (360, 166), (480, 184), (570, 196), (640, 202), (690, 205),
        ],
        et_points=[
            (0, 196), (20, 150), (78, 138), (120, 152), (240, 184),
            (360, 198), (480, 214), (570, 222), (640, 226), (690, 228),
        ],
        # 约 8s 短失联（插值补线）与约 16s 较长失联（默认 12s 阈值下留空）
        gaps=[(188, 196), (430, 446)],
        spikes=[(143, 4.2, 0.0), (512, 0.0, 11.0)],
        anchors=[
            ("charge", 0.0, 185.0, "合成预置：下豆"),
            ("turn", 78.0, 96.0, "合成预置：回温点（豆温谷底）"),
            ("first_crack", 570.0, 196.0, "合成预置：听到一爆开始"),
            ("drop", 690.0, 205.0, "合成预置：出锅"),
        ],
        dampers=[(0.0, 65.0), (120.0, 55.0)],
        markers=[(300.0, "颜色转为浅棕，青草气消退")],
    )

    # —— 批次 B：更早收风门（45s，回温前），缺口含一段 28s 长失联（不插值）——
    b = SynthSpec(
        code="A-20260927-02",
        profile_name="日晒耶加雪菲·中度（风门提前试验）",
        bean_origin="埃塞俄比亚 耶加雪菲",
        charge_g=1200.0,
        target_drop_c=205.0,
        roast_date="2026-09-27",
        description="对比批次：风门提前至回温前调整，用于叠加观察，不推断因果。",
        bt_points=[
            (0, 187), (20, 114), (84, 99), (120, 122), (240, 152),
            (360, 170), (470, 186), (552, 196), (612, 201), (660, 205),
        ],
        et_points=[
            (0, 198), (20, 152), (84, 141), (120, 156), (240, 187),
            (360, 202), (470, 217), (552, 224), (612, 227), (660, 229),
        ],
        # 约 8s、6s 两段短失联（默认 12s 阈值下插值补线）；约 30s 长失联留空
        gaps=[(90, 98), (348, 378), (598, 604)],
        spikes=[(231, -3.6, 0.0)],
        anchors=[
            ("charge", 0.0, 187.0, "合成预置：下豆"),
            ("turn", 84.0, 99.0, "合成预置：回温点（豆温谷底）"),
            ("first_crack", 552.0, 196.0, "合成预置：听到一爆开始"),
            ("drop", 660.0, 205.0, "合成预置：出锅"),
        ],
        dampers=[(0.0, 65.0), (45.0, 55.0)],
        markers=[(285.0, "银皮较多，留意排烟")],
    )
    return [a, b]


def generate_batch(session, spec: SynthSpec, seed: int) -> Batch:
    rng = np.random.default_rng(seed)
    end_t = max(p[0] for p in spec.bt_points)

    # 1) 非均匀时间轴：2s 基线 + 抖动
    raw_t = np.arange(0.0, end_t + 0.1, spec.sample_base_s)
    jitter = rng.normal(0.0, 0.45, raw_t.shape)
    jitter[0] = 0.0
    times = np.round(raw_t + jitter, 2)
    times = np.clip(times, 0.0, None)
    times = np.sort(np.unique(times))

    # 2) 剔除失联缺口内的采样（缺测不写库）
    keep = np.ones(times.shape, dtype=bool)
    for gs, ge in spec.gaps:
        keep &= ~((times > gs) & (times < ge))
    times = times[keep]

    # 3) 合成真实曲线 + 噪声（白噪声 + 慢漂移）
    bt = _pchip_like_grid(spec.bt_points, times)
    et = _pchip_like_grid(spec.et_points, times)
    drift_bt = 0.8 * np.sin(times / 150.0) + 0.5 * np.sin(times / 47.0)
    drift_et = 1.0 * np.sin(times / 170.0 + 0.6)
    bt += rng.normal(0.0, spec.noise_bt, times.shape) + drift_bt
    et += rng.normal(0.0, spec.noise_et, times.shape) + drift_et

    # 4) 跳变点（保留并标记，绝不静默修改）
    spike_set = {}
    for st, db, de in spec.spikes:
        i = int(np.argmin(np.abs(times - st)))
        bt[i] += db
        et[i] += de
        spike_set[i] = True

    batch = Batch(
        code=spec.code,
        profile_name=spec.profile_name,
        bean_origin=spec.bean_origin,
        charge_g=spec.charge_g,
        target_drop_c=spec.target_drop_c,
        roast_date=spec.roast_date,
        description=spec.description,
        synth_seed=seed,
    )

    batch.samples = [
        Sample(
            t_s=round(float(t), 2),
            bean_temp_c=round(float(b), 1),
            env_temp_c=round(float(e), 1),
            quality="spike" if i in spike_set else "ok",
        )
        for i, (t, b, e) in enumerate(zip(times, bt, et))
    ]

    batch.events = []
    for etype, etime, val, note in spec.anchors:
        batch.events.append(
            Event(
                event_type=etype,
                event_time=round(float(etime), 2),
                value=None if val is None else round(float(val), 1),
                source="auto",
                operator="synth",
                note=note,
                method={"generator": "synthetic", "seed": seed},
                is_current=True,
            )
        )
    for dt, damper in spec.dampers:
        batch.events.append(
            Event(
                event_type="damper",
                event_time=round(float(dt), 2),
                value=round(float(damper), 1),
                source="auto",
                operator="synth",
                note="风门设定值（%）",
                method={"generator": "synthetic", "seed": seed},
                is_current=True,
            )
        )
    for mt, note in spec.markers:
        batch.events.append(
            Event(
                event_type="marker",
                event_time=round(float(mt), 2),
                value=None,
                source="auto",
                operator="synth",
                note=note,
                method={"generator": "synthetic", "seed": seed},
                is_current=True,
            )
        )

    session.add(batch)
    session.flush()
    return batch


def seed_if_empty(session) -> int:
    if session.query(Batch).count() > 0:
        return 0
    n = 0
    for i, spec in enumerate(_specs()):
        generate_batch(session, spec, seed=20260927 + i)
        n += 1
    session.commit()
    return n
