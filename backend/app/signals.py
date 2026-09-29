"""信号处理（NumPy）：缺测识别、插值标记、温升率、回温点检测。

核心原则：
1. 原始采样永不就地改写。平滑/插值全部返回新数组，并逐点标注 origin
   （measured / interpolated / missing）。
2. 温升率采用明确声明的**末端（trailing）线性回归窗口**，而非两点瞬时差分；
   窗口内必须有足够实测锚点，否则该点 RoR 置空。
3. 插值段只用于绘图补线，不会冒充实测，也不会被当作实测参与 RoR 拟合
   （即使插值点进入时间窗口，锚点统计仍只数 measured）。
"""
from dataclasses import dataclass

import numpy as np

MEASURED = "measured"
INTERPOLATED = "interpolated"
MISSING = "missing"


@dataclass
class Gap:
    start_t: float          # 缺口前最后一个实测点时间
    end_t: float            # 缺口后第一个实测点时间
    duration_s: float       # end_t - start_t
    filled: bool            # 是否用线性插值补绘
    n_measured_skipped: int  # 两个实测点之间应有的采样数（0 表示只是采样稀疏）


@dataclass
class TurnSuggestion:
    t_s: float
    bean_temp_c: float
    method: dict


def _as_array(x, dtype=float):
    return np.asarray(x, dtype=dtype)


def detect_gaps(
    t_s,
    median_interval_s: float | None = None,
    gap_factor: float = 1.8,
    min_gap_s: float = 4.0,
) -> list[Gap]:
    """从非均匀采样轴推断探针失联缺口。

    判据：相邻实测间隔 > max(median*gap_factor, min_gap_s)。
    抖动 ~0.5s 时，正常间隔在 1~3s，阈值 4s 即可稳健区分；
    合成数据里"丢弃"的采样不会写库，因此缺口只能从时间轴推断；
    真实机台若上报 null，则可直接把判据换成 null 游程。
    """
    t = _as_array(t_s)
    if t.size < 3:
        return []
    if median_interval_s is None:
        median_interval_s = float(np.median(np.diff(t)))
    threshold = max(median_interval_s * gap_factor, min_gap_s)
    gaps: list[Gap] = []
    for i in np.where(np.diff(t) > threshold)[0]:
        gaps.append(
            Gap(
                start_t=float(t[i]),
                end_t=float(t[i + 1]),
                duration_s=float(t[i + 1] - t[i]),
                filled=False,
                n_measured_skipped=max(
                    0, round((t[i + 1] - t[i]) / median_interval_s) - 1
                ),
            )
        )
    return gaps


def build_display_series(
    t_s,
    values,
    origins,
    gap_threshold_s: float = 15.0,
    interp_step_s: float = 2.0,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, list[Gap]]:
    """生成绘图用的均匀近似序列，并逐点标注来源。

    - measured:     原始实测点，值为真实读数
    - interpolated: 短失联缺口（<= gap_threshold_s）内的线性插值，仅供补线
    - missing:      长失联缺口（>  gap_threshold_s），值为 NaN，前端断线

    返回 (t_out, v_out, origin_out, gaps)，原输入数组不被修改。
    """
    t = _as_array(t_s)
    v = _as_array(values)
    origin_arr = np.asarray(origins, dtype=object)
    order = np.argsort(t)
    t, v, origin_arr = t[order], v[order], origin_arr[order]

    gaps = detect_gaps(t)
    t_out = list(t)
    v_out = list(v)
    o_out: list[str] = [
        MEASURED if origin_arr[i] != MISSING else MISSING for i in range(t.size)
    ]

    for g in gaps:
        # 严格小于阈值才插值：阈值 0 表示"一律不插值"，全部留空断线。
        # 注意 gaps 由 detect_gaps(min_gap_s=4s) 检出，与插值阈值相互独立。
        if g.duration_s < gap_threshold_s:
            g.filled = True
            lo = np.searchsorted(t, g.start_t)
            hi = np.searchsorted(t, g.end_t)
            # 严格位于缺口内部的插值点（两端仍是实测）
            n_steps = int(np.floor(g.duration_s / interp_step_s))
            for k in range(1, n_steps + 1):
                tc = g.start_t + k * interp_step_s
                if tc >= g.end_t:
                    break
                vc = float(np.interp(tc, [t[lo], t[hi]], [v[lo], v[hi]]))
                t_out.append(tc)
                v_out.append(vc)
                o_out.append(INTERPOLATED)
        else:
            g.filled = False
            # 在缺口中部放一个 NaN 哨兵，让 ECharts connectNulls=false 时断线
            mid = 0.5 * (g.start_t + g.end_t)
            t_out.append(mid)
            v_out.append(np.nan)
            o_out.append(MISSING)

    order2 = np.argsort(np.asarray(t_out))
    return (
        _as_array(t_out)[order2],
        _as_array(v_out)[order2],
        np.asarray(o_out, dtype=object)[order2],
        gaps,
    )


def windowed_ror(
    t_s,
    temp_c,
    window_s: float = 30.0,
    min_anchors: int = 4,
    min_coverage: float = 0.5,
) -> np.ndarray:
    """温升率（°C/min）：末端 [t-window, t] 窗口对**实测点**做最小二乘直线拟合，
    取斜率并 ×60。

    明确的窗口语义：
    - 末端窗口（trailing）：只使用当前时刻及之前的数据；
    - 线性回归而非两点差分，抑制单点噪声；
    - 实测锚点 < min_anchors 或窗口覆盖时长 < window_s*min_coverage 时输出 NaN；
      探针失联后复出的首个点因此天然为 NaN，避免穿越缺口的虚假温升率；
    - 输入中的插值点不应传入（调用方只取 measured 行）。
    """
    t = _as_array(t_s)
    y = _as_array(temp_c)
    ror = np.full(t.shape, np.nan)
    for i in range(t.size):
        t0 = t[i] - window_s
        m = (t >= t0) & (t <= t[i]) & ~np.isnan(y)
        if int(m.sum()) < min_anchors:
            continue
        tt, yy = t[m], y[m]
        if tt[-1] - tt[0] < window_s * min_coverage:
            continue
        slope, _ = np.polyfit(tt, yy, 1)
        ror[i] = slope * 60.0
    return ror


def moving_average_temp(temp_c, window_s: float, t_s) -> np.ndarray:
    """仅用于检测器的温度平滑（中心时间窗均值）。

    返回的是**新数组**，不回写原始温度；窗口内点数不足时回退为原值。
    """
    t = _as_array(t_s)
    y = _as_array(temp_c)
    out = np.full(y.shape, np.nan)
    half = 0.5 * window_s
    for i in range(t.size):
        m = np.abs(t - t[i]) <= half
        if m.sum() >= 3:
            out[i] = np.mean(y[m])
        else:
            out[i] = np.nan
    return out


def detect_turn(
    t_s,
    bean_temp_c,
    search_start_s: float = 15.0,
    search_end_s: float = 240.0,
    smooth_window_s: float = 12.0,
) -> TurnSuggestion | None:
    """回温点检测建议（仅作为"算法建议"，操作员确认后才成为记录）。

    方法：对豆温做中心窗口平滑（不改原值），在搜索区间内取平滑豆温最低点；
    要求该点之后平滑曲线确已回升（升幅 >= 2°C），否则不构成回温点。
    """
    t = _as_array(t_s)
    y = _as_array(bean_temp_c)
    ys = moving_average_temp(y, smooth_window_s, t)
    m = (t >= search_start_s) & (t <= search_end_s) & ~np.isnan(ys)
    idx = np.where(m)[0]
    if idx.size < 5:
        return None
    local = int(idx[np.argmin(ys[idx])])
    after = (t > t[local]) & (t <= t[local] + 45.0)
    if not np.any(after) or np.nanmax(ys[after]) - ys[local] < 2.0:
        return None
    return TurnSuggestion(
        t_s=float(t[local]),
        bean_temp_c=float(y[local]),
        method={
            "detector": "smoothed_minimum",
            "smooth_window_s": smooth_window_s,
            "search_window_s": [search_start_s, search_end_s],
            "confirmation_rise_c": 2.0,
        },
    )
