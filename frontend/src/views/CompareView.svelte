<script>
  import { api } from '../api.js';
  import EChart from '../lib/EChart.svelte';
  import { buildEventMarks } from '../lib/charts.js';
  import { fmtDur, fmtPct } from '../lib/format.js';

  export let batches; // [{id, code}]

  let aId = null;
  let bId = null;
  let data = null;
  let loading = false;
  let error = '';
  let rorWindow = 30;
  let maxGap = 15;

  $: if (batches.length && aId == null) {
    aId = batches[0].id;
    bId = batches[batches.length - 1].id;
  }

  async function load() {
    if (aId == null || bId == null || aId === bId) {
      error = '请选择两个不同的批次';
      data = null;
      return;
    }
    loading = true;
    error = '';
    try {
      data = await api.compare(aId, bId, {
        rorWindow: Number(rorWindow),
        maxGap: Number(maxGap),
      });
    } catch (e) {
      error = e.message;
    } finally {
      loading = false;
    }
  }
  $: aId, bId, rorWindow, maxGap, load();
  let t;
  function schedule() { clearTimeout(t); t = setTimeout(load, 150); }

  function seriesOf(payload, kind /* 'bean' | 'env' | 'ror' */, color) {
    if (kind === 'ror') {
      return [{
        name: `${payload.code} 豆温RoR`,
        type: 'line',
        showSymbol: false,
        connectNulls: false,
        lineStyle: { width: 1.7, color },
        itemStyle: { color },
        data: payload.ror.map((r) => [r.t_s, r.bean_ror_c_per_min]),
      }];
    }
    const src = kind === 'bean' ? payload.display_bean : payload.display_env;
    const measured = [];
    const interp = [];
    for (const p of src) {
      const v = p.v == null ? null : p.v;
      measured.push(p.origin === 'measured' ? [p.t_s, v] : [p.t_s, null]);
      interp.push(p.origin === 'interpolated' ? [p.t_s, v] : [p.t_s, null]);
    }
    // 为插值虚线缝上两端实测锚点
    for (let i = 0; i < src.length; i++) {
      if (src[i].origin !== 'interpolated') continue;
      let j = i;
      while (j < src.length && src[j].origin === 'interpolated') j++;
      if (i - 1 >= 0 && src[i - 1].v != null) interp[i - 1] = [src[i - 1].t_s, src[i - 1].v];
      if (j < src.length && src[j].v != null) interp[j] = [src[j].t_s, src[j].v];
      i = j;
    }
    return [
      {
        name: `${payload.code} ${kind === 'bean' ? '豆温' : '环温'}（实测）`,
        type: 'line', showSymbol: false, connectNulls: false,
        lineStyle: { width: 2, color }, itemStyle: { color },
        data: measured,
      },
      {
        name: `${payload.code} 插值（非实测）`,
        type: 'line', showSymbol: false, connectNulls: false,
        lineStyle: { width: 1.2, color, type: 'dashed', opacity: 0.65 },
        itemStyle: { color }, data: interp,
      },
    ];
  }

  $: tempOpt = data && (() => {
    const [pa, pb] = data.batches;
    const ma = buildEventMarks(pa.events);
    const mb = buildEventMarks(pb.events);
    const series = [
      ...seriesOf(pa, 'bean', '#d64545'),
      ...seriesOf(pa, 'env', '#e89a9a'),
      ...seriesOf(pb, 'bean', '#3d6ce0'),
      ...seriesOf(pb, 'env', '#8fb0ee'),
    ];
    series[0].markLine = ma.markLine;
    series[0].markArea = ma.markArea;
    series[2].markLine = mb.markLine;
    series[2].markArea = mb.markArea;
    return {
      animation: false,
      tooltip: { trigger: 'axis', valueFormatter: (v) => (v == null ? '缺测' : `${Number(v).toFixed(1)}°C`) },
      legend: { top: 0, textStyle: { fontSize: 10.5 } },
      grid: { left: 52, right: 24, top: 60, bottom: 48 },
      xAxis: { type: 'value', name: '下豆后秒', nameLocation: 'middle', nameGap: 28 },
      yAxis: { type: 'value', name: '温度 °C' },
      dataZoom: [{ type: 'inside' }, { type: 'slider', height: 18, bottom: 8 }],
      series,
    };
  })();

  $: rorOpt = data && (() => {
    const [pa, pb] = data.batches;
    return {
      animation: false,
      tooltip: { trigger: 'axis', valueFormatter: (v) => (v == null ? '空' : `${Number(v).toFixed(2)} °C/min`) },
      legend: { top: 0 },
      grid: { left: 52, right: 24, top: 34, bottom: 40 },
      xAxis: { type: 'value', name: '下豆后秒', nameLocation: 'middle', nameGap: 26 },
      yAxis: { type: 'value', name: '°C/min' },
      dataZoom: [{ type: 'inside' }],
      series: [...seriesOf(pa, 'ror', '#d64545'), ...seriesOf(pb, 'ror', '#3d6ce0')],
    };
  })();
</script>

<div class="panel">
  <h2>双批次对比</h2>
  <div class="compare-pick">
    <div>
      <label style="font-size:12px;color:var(--ink-2)">批次 A（红）</label>
      <select bind:value={aId}>
        {#each batches as b}<option value={b.id}>{b.code}</option>{/each}
      </select>
    </div>
    <div>
      <label style="font-size:12px;color:var(--ink-2)">批次 B（蓝）</label>
      <select bind:value={bId}>
        {#each batches as b}<option value={b.id}>{b.code}</option>{/each}
      </select>
    </div>
    <div>
      <label style="font-size:12px;color:var(--ink-2)">RoR 窗口（秒）</label>
      <input type="number" min="5" max="300" bind:value={rorWindow} on:input={schedule} style="width:80px" />
    </div>
    <div>
      <label style="font-size:12px;color:var(--ink-2)">最大插值缺口（秒）</label>
      <input type="number" min="0" max="120" bind:value={maxGap} on:input={schedule} style="width:80px" />
    </div>
  </div>
  {#if error}<div class="error">{error}</div>{/if}
  <div class="disclaimer" style="margin-top:10px">
    {data?.disclaimer ?? '两批次曲线按各自下豆后的秒数对齐并置，仅用于观察风门调整前后的形态；不宣称因果。'}
  </div>
</div>

{#if loading && !data}<div class="panel">加载中…</div>{/if}

{#if data}
  <div class="panel">
    <h2>豆温 / 环温叠加（实线=实测，虚线=插值非实测；色块=风门区间）</h2>
    <EChart option={tempOpt} height="500px" />
  </div>
  <div class="panel">
    <h2>豆温温升率叠加 · {data.ror_method.window_s}s 末端窗口回归</h2>
    <EChart option={rorOpt} height="260px" />
  </div>

  <div class="panel">
    <h2>阶段指标对照</h2>
    <table class="events">
      <thead>
        <tr><th>指标</th><th>{data.batches[0].code}</th><th>{data.batches[1].code}</th></tr>
      </thead>
      <tbody>
        {#each [
          ['drying_s', '干燥区间', (v) => fmtDur(v)],
          ['maillard_s', '梅纳区间', (v) => fmtDur(v)],
          ['development_s', '发展区间', (v) => fmtDur(v)],
          ['total_s', '总烘焙时长', (v) => fmtDur(v)],
        ] as [key, label, f]}
          <tr>
            <td>{label}</td>
            {#each data.batches as p}
              <td>{f(p.metrics.intervals[key]?.value)}</td>
            {/each}
          </tr>
        {/each}
        <tr>
          <td><b>发展时间比 DTR</b></td>
          {#each data.batches as p}
            <td><b>{fmtPct(p.metrics.development_time_ratio)}</b></td>
          {/each}
        </tr>
        <tr>
          <td>回温点 / 一爆 / 出锅</td>
          {#each data.batches as p}
            <td>
              {p.metrics.anchors.turn?.t_s ?? '—'}s /
              {p.metrics.anchors.first_crack?.t_s ?? '—'}s /
              {p.metrics.anchors.drop?.t_s ?? '—'}s
            </td>
          {/each}
        </tr>
      </tbody>
    </table>
    <p style="font-size:11.5px;color:var(--ink-2);margin-top:8px">
      所有区间均以「下豆→回温点→一爆→出锅」四个锚点的当前生效时间显式计算；
      指标差异与风门时序的对应关系仅供观察，不作因果归因。
    </p>
  </div>
{/if}
