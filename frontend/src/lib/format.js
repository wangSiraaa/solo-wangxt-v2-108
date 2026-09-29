export const EVENT_LABELS = {
  charge: '下豆',
  turn: '回温点',
  first_crack: '一爆',
  drop: '出锅',
  damper: '风门',
  marker: '人工标记',
};

export const EVENT_COLORS = {
  charge: '#5b8def',
  turn: '#e0a417',
  first_crack: '#e05c17',
  drop: '#7b4dd6',
  damper: '#0f9d8f',
  marker: '#888',
};

export function fmtTime(t) {
  if (t == null || Number.isNaN(t)) return '--:--';
  const m = Math.floor(t / 60);
  const s = Math.round(t % 60);
  return `${m}:${String(s).padStart(2, '0')}`;
}

export function fmtDur(sec) {
  if (sec == null) return '--';
  const m = Math.floor(sec / 60);
  const s = Math.round(sec % 60);
  return `${m}分${s.toString().padStart(2, '0')}秒`;
}

export function fmtPct(x) {
  return x == null ? '--' : `${(x * 100).toFixed(1)}%`;
}

/** 将 display_* 序列拆成 ECharts 需要的 measured / 插值段 / 缺测段 */
export function splitByOrigin(displayPoints) {
  const measured = [];
  const interp = [];
  const gaps = [];
  let lastMeasured = null;
  for (const p of displayPoints) {
    const point = p.v == null ? [p.t_s, null] : [p.t_s, p.v];
    if (p.origin === 'measured') {
      measured.push(point);
      interp.push([p.t_s, null]);
      lastMeasured = point;
    } else if (p.origin === 'interpolated') {
      measured.push([p.t_s, null]);
      interp.push(point);
    } else {
      // missing 哨兵：前后各留一个锚点以便 ECharts markArea 定位
      measured.push([p.t_s, null]);
      interp.push([p.t_s, null]);
      gaps.push(p.t_s);
    }
  }
  return { measured, interp, missingCenters: gaps };
}

export function rorPoints(ror) {
  return ror.map((r) => ({
    value: [r.t_s, r.bean_ror_c_per_min],
  }));
}
