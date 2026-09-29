<script>
  import { fmtDur, fmtPct, fmtTime } from './format.js';

  export let metrics;

  const ANCHOR_META = [
    ['charge', '下豆'],
    ['turn', '回温点'],
    ['first_crack', '一爆'],
    ['drop', '出锅'],
  ];
</script>

<div class="panel">
  <h2>阶段指标</h2>
  {#if metrics.errors.length > 0}
    <div class="error" style="margin-bottom:8px">
      {#each metrics.errors as err}<div>⚠ {err}</div>{/each}
    </div>
  {/if}
  <div class="metric-grid">
    {#each Object.entries(metrics.intervals) as [key, iv]}
      <div class="metric" class:highlight={key === 'development_s'}>
        <div class="k">{iv.label}</div>
        <div class="v">{fmtDur(iv.value)}</div>
        <div class="sub">{iv.value == null ? '' : `${iv.value.toFixed(1)} s`}</div>
      </div>
    {/each}
    <div class="metric highlight">
      <div class="k">发展时间比 DTR</div>
      <div class="v">{fmtPct(metrics.development_time_ratio)}</div>
      <div class="sub">(出锅−一爆)/(出锅−下豆)</div>
    </div>
  </div>

  <h3>锚点来源</h3>
  <table class="events">
    <thead>
      <tr><th>锚点</th><th>时间</th><th>豆温（最近实测点）</th><th>来源</th><th>操作员</th><th>备注</th></tr>
    </thead>
    <tbody>
      {#each ANCHOR_META as [key, label]}
        {@const a = metrics.anchors[key]}
        <tr>
          <td>{label}</td>
          <td>{a ? fmtTime(a.t_s) : '—'}</td>
          <td>
            {#if a}{a.bean_temp_c}°C
              <span class="sub">(读数于 {fmtTime(a.temp_sample_t_s)})</span>{:else}—{/if}
          </td>
          <td>
            {#if a}<span class="pill {a.source}">{a.source === 'auto' ? '合成预置' : '人工'}</span>{:else}—{/if}
          </td>
          <td>{a?.operator || '—'}</td>
          <td>{a?.note || ''}</td>
        </tr>
      {/each}
    </tbody>
  </table>
  <p style="font-size:11.5px;color:var(--ink-2);margin-top:8px">
    {metrics.development_time_ratio_definition}。锚点温度取最近实测读数、不做插值；
    指标区间完全由当前生效的锚点时间决定。
  </p>
</div>
