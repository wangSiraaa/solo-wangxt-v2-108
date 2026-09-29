import { EVENT_COLORS } from './format.js';

const AXIS_STYLE = {
  axisLine: { lineStyle: { color: '#c3c9d4' } },
  splitLine: { lineStyle: { color: '#eef0f4' } },
  axisLabel: { color: '#555d70' },
};

/** 事件 markLine（垂直虚线）+ 风门 markArea（相邻两条 damper 之间） */
export function buildEventMarks(events, { damperShade = true } = {}) {
  const current = events.filter((e) => e.is_current);
  const lines = [];
  for (const e of current) {
    if (e.event_type === 'damper') continue;
    const isAnchor = ['charge', 'turn', 'first_crack', 'drop'].includes(e.event_type);
    lines.push({
      xAxis: e.event_time,
      label: {
        formatter: labelOf(e),
        position: isAnchor ? 'insideEndTop' : 'insideStartBottom',
        color: EVENT_COLORS[e.event_type] || '#888',
        fontSize: 10,
      },
      lineStyle: {
        color: EVENT_COLORS[e.event_type] || '#aaa',
        type: isAnchor ? 'solid' : 'dotted',
        width: isAnchor ? 1.6 : 1,
      },
    });
  }

  const markLine = {
    symbol: 'none',
    silent: true,
    data: lines,
    animation: false,
  };

  let markArea;
  const dampers = current
    .filter((e) => e.event_type === 'damper')
    .sort((a, b) => a.event_time - b.event_time);
  if (damperShade && dampers.length > 1) {
    // 用极淡色块标记风门区间，并在区间顶部标注档位；仅可视化，不暗示因果
    const data = [];
    for (let i = 0; i < dampers.length - 1; i++) {
      data.push([
        {
          xAxis: dampers[i].event_time,
          itemStyle: i % 2 === 0 ? { color: 'rgba(15,157,143,0.06)' } : { color: 'rgba(15,157,143,0.12)' },
          label: { show: true, formatter: `风门 ${dampers[i].value}%`, color: '#0f7a70', fontSize: 10, position: 'insideTop' },
        },
        { xAxis: dampers[i + 1].event_time },
      ]);
    }
    markArea = { silent: true, data, animation: false };
  }
  return { markLine, markArea };
}

function labelOf(e) {
  const map = {
    charge: '下豆',
    turn: '回温点',
    first_crack: '一爆',
    drop: '出锅',
    marker: '标记',
  };
  const m = Math.floor(e.event_time / 60);
  const s = Math.round(e.event_time % 60).toString().padStart(2, '0');
  return `${map[e.event_type] || e.event_type} ${m}:${s}`;
}

/** 豆温/环温主图：实测实线 + 插值虚线 + 缺测灰段 + 事件线 */
export function tempChartOption(detail) {
  const { display_bean, display_env, events, gaps } = detail;
  const { markLine, markArea } = buildEventMarks(events);

  const beanMeasured = [];
  const beanInterp = [];
  const envMeasured = [];
  const envInterp = [];
  const missingAreas = gaps.filter((g) => !g.filled).map((g) => [
    { xAxis: g.start_t_s, itemStyle: { color: 'rgba(120,120,120,0.14)' } },
    { xAxis: g.end_t_s, label: { show: true, formatter: '失联', color: '#888', fontSize: 10, position: 'insideTop' } },
  ]);

  for (const p of display_bean) {
    const v = p.v == null ? null : p.v;
    beanMeasured.push(p.origin === 'measured' ? [p.t_s, v] : [p.t_s, null]);
    beanInterp.push(p.origin === 'interpolated' ? [p.t_s, v] : [p.t_s, null]);
  }
  for (const p of display_env) {
    const v = p.v == null ? null : p.v;
    envMeasured.push(p.origin === 'measured' ? [p.t_s, v] : [p.t_s, null]);
    envInterp.push(p.origin === 'interpolated' ? [p.t_s, v] : [p.t_s, null]);
  }
  // ECharts connectNulls=false 时虚线两端需要锚点：把缺口边界值补进插值序列
  stitchInterp(display_bean, beanInterp);
  stitchInterp(display_env, envInterp);

  const series = [
    {
      name: '豆温（实测）', type: 'line', data: beanMeasured,
      showSymbol: false, connectNulls: false,
      lineStyle: { width: 2.2, color: '#d64545' },
      itemStyle: { color: '#d64545' },
      markLine, markArea,
    },
    {
      name: '豆温（插值，非实测）', type: 'line', data: beanInterp,
      showSymbol: false, connectNulls: false,
      lineStyle: { width: 1.4, color: '#d64545', type: 'dashed', opacity: 0.75 },
      itemStyle: { color: '#d64545' },
      markArea: { silent: true, animation: false, data: missingAreas },
    },
    {
      name: '环境温度（实测）', type: 'line', data: envMeasured,
      showSymbol: false, connectNulls: false,
      lineStyle: { width: 2, color: '#3d6ce0' },
      itemStyle: { color: '#3d6ce0' },
    },
    {
      name: '环境温度（插值，非实测）', type: 'line', data: envInterp,
      showSymbol: false, connectNulls: false,
      lineStyle: { width: 1.3, color: '#3d6ce0', type: 'dashed', opacity: 0.7 },
      itemStyle: { color: '#3d6ce0' },
    },
  ];

  return {
    animation: false,
    tooltip: {
      trigger: 'axis',
      valueFormatter: (v) => (v == null ? '缺测' : `${Number(v).toFixed(1)} °C`),
    },
    legend: { top: 0, textStyle: { fontSize: 11 } },
    grid: { left: 52, right: 24, top: 42, bottom: 48 },
    xAxis: {
      type: 'value', name: '时间（下豆后秒）', nameLocation: 'middle', nameGap: 28,
      ...AXIS_STYLE,
    },
    yAxis: { type: 'value', name: '温度 °C', ...AXIS_STYLE },
    dataZoom: [{ type: 'inside' }, { type: 'slider', height: 18, bottom: 8 }],
    series,
  };
}

/** 让插值虚线跨越缺口显示：把每个插值游程两端替换为相邻实测值 */
function stitchInterp(display, target) {
  for (let i = 0; i < display.length; i++) {
    if (display[i].origin !== 'interpolated') continue;
    let j = i;
    while (j < display.length && display[j].origin === 'interpolated') j++;
    const lo = i - 1;
    const hi = j;
    if (lo >= 0 && display[lo].v != null) target[lo] = [display[lo].t_s, display[lo].v];
    if (hi < display.length && display[hi].v != null) target[hi] = [display[hi].t_s, display[hi].v];
    i = j;
  }
}

/** 温升率图：仅实测锚点的窗口回归值，失联后复出为空（断线） */
export function rorChartOption(detail, channel = 'bean') {
  const key = channel === 'bean' ? 'bean_ror_c_per_min' : 'env_ror_c_per_min';
  const data = detail.ror.map((r) => [r.t_s, r[key]]);
  const { markLine } = buildEventMarks(detail.events, { damperShade: false });
  const color = channel === 'bean' ? '#d64545' : '#3d6ce0';
  const w = detail.ror_method.window_s;
  return {
    animation: false,
    tooltip: {
      trigger: 'axis',
      valueFormatter: (v) => (v == null ? '空（锚点不足）' : `${Number(v).toFixed(2)} °C/min`),
    },
    grid: { left: 52, right: 24, top: 30, bottom: 44 },
    xAxis: { type: 'value', name: '秒', nameGap: 26, nameLocation: 'middle', ...AXIS_STYLE },
    yAxis: { type: 'value', name: '°C/min', ...AXIS_STYLE },
    dataZoom: [{ type: 'inside' }],
    series: [{
      name: `温升率（${w}s 末端窗口回归）`,
      type: 'line', data, showSymbol: false, connectNulls: false,
      lineStyle: { width: 1.8, color }, itemStyle: { color },
      markLine,
    }],
  };
}
