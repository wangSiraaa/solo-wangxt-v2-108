<script>
  import { api, downloadUrl } from '../api.js';
  import EChart from '../lib/EChart.svelte';
  import EventPanel from '../lib/EventPanel.svelte';
  import MetricsPanel from '../lib/MetricsPanel.svelte';
  import { tempChartOption, rorChartOption } from '../lib/charts.js';
  import { fmtTime } from '../lib/format.js';

  export let batchId;

  let detail = null;
  let loading = false;
  let error = '';
  let formMsg = '';
  let formErr = '';

  let rorWindow = 30;
  let maxGap = 15;

  async function load() {
    if (!batchId) return;
    loading = true;
    error = '';
    try {
      detail = await api.batchDetail(batchId, {
        rorWindow: Number(rorWindow),
        maxGap: Number(maxGap),
      });
    } catch (e) {
      error = e.message;
    } finally {
      loading = false;
    }
  }

  $: if (batchId) load();

  // 参数变化后重新拉取（原始采样不变，仅派生序列重算）
  let reloadTimer;
  function scheduleReload() {
    clearTimeout(reloadTimer);
    reloadTimer = setTimeout(load, 150);
  }

  async function onSubmit(e) {
    formErr = '';
    formMsg = '';
    try {
      await api.addEvent(batchId, e.detail);
      formMsg = '已记录修正（旧锚点已转为历史，来源保留）';
      await load();
    } catch (err) {
      formErr = err.message;
    }
  }

  async function onAcceptSuggestion(e) {
    const op = prompt('采用算法建议也需要留名。请输入操作员姓名：');
    if (!op || !op.trim()) return;
    formErr = '';
    try {
      // 先以建议值创建一条人工 turn 记录
      await api.addEvent(batchId, {
        event_type: 'turn',
        event_time: e.detail.t_s,
        value: e.detail.bean_temp_c,
        operator: op.trim(),
        note: '操作员确认检测器建议（smoothed_minimum）',
      });
      formMsg = '已将建议确认为人工回温点';
      await load();
    } catch (err) {
      formErr = err.message;
    }
  }

  async function onRevert(e) {
    formErr = '';
    try {
      await api.revertEvent(e.detail.id, e.detail.operator);
      formMsg = '已恢复历史版本，操作已留痕';
      await load();
    } catch (err) {
      formErr = err.message;
    }
  }

  $: tempOpt = detail && tempChartOption(detail);
  $: rorOpt = detail && rorChartOption(detail, 'bean');
</script>

{#if error}<div class="panel error">{error}</div>{/if}
{#if loading && !detail}<div class="panel">加载中…</div>{/if}

{#if detail}
  <div class="panel">
    <h2>{detail.code} · {detail.profile_name_full}</h2>
    <div style="color:var(--ink-2);font-size:12.5px">
      {detail.bean_origin} · 豆量 {detail.charge_g}g · 目标出锅 {detail.target_drop_c}°C
      · {detail.n_samples} 个原始采样 · {detail.gaps.length} 段推断失联 ·
      合成种子 #{detail.synth_seed}
    </div>
    <p style="font-size:12px;color:var(--ink-2);margin:6px 0 0">{detail.description}</p>

    <div class="controls" style="margin-top:12px">
      <div>
        <label>温升率末端窗口（秒）</label>
        <input type="number" min="5" max="300" bind:value={rorWindow} on:input={scheduleReload} />
      </div>
      <div>
        <label>最大插值缺口（秒，0=全部留空）</label>
        <input type="number" min="0" max="120" bind:value={maxGap} on:input={scheduleReload} />
      </div>
      <div class="note">调整只重算派生曲线，数据库原始温度永不改变</div>
      <div style="margin-left:auto">
        <a href={downloadUrl(batchId, 'json')}><button class="ghost" type="button">导出复现包 JSON</button></a>
        <a href={`/api/batches/${batchId}/export/samples.csv`}><button class="ghost" type="button">原始采样 CSV</button></a>
        <a href={`/api/batches/${batchId}/export/events.csv`}><button class="ghost" type="button">事件历史 CSV</button></a>
      </div>
    </div>
  </div>

  <div class="panel">
    <h2>豆温 / 环境温度曲线（与操作事件对齐）</h2>
    <EChart option={tempOpt} height="460px" />
    <div class="legend-note">
      <span><i class="sw" style="border-color:#d64545"></i>豆温实测</span>
      <span><i class="sw" style="border-color:#d64545;border-top-style:dashed"></i>豆温插值（非实测）</span>
      <span><i class="sw" style="border-color:#3d6ce0"></i>环温实测</span>
      <span><i class="sw" style="border-color:#3d6ce0;border-top-style:dashed"></i>环温插值（非实测）</span>
      <span style="color:#888">▌ 灰带 = 探针失联，留空断线</span>
      <span style="color:#0f7a70">▌ 青色带 = 风门档位区间（仅标注）</span>
    </div>
    {#if detail.gaps.length}
      <h3>采样缺口（由非均匀时间轴推断）</h3>
      <table class="events">
        <thead><tr><th>起点</th><th>终点</th><th>时长</th><th>处理</th><th>约缺采样数</th></tr></thead>
        <tbody>
          {#each detail.gaps as g}
            <tr>
              <td>{fmtTime(g.start_t_s)}</td>
              <td>{fmtTime(g.end_t_s)}</td>
              <td>{g.duration_s.toFixed(1)} s</td>
              <td>
                {#if g.filled}
                  <span class="pill auto">线性插值补线（非实测）</span>
                {:else}
                  <span class="pill danger">超过 {maxGap}s，留空</span>
                {/if}
              </td>
              <td>{g.n_measured_skipped}</td>
            </tr>
          {/each}
        </tbody>
      </table>
    {/if}
  </div>

  <div class="panel">
    <h2>温升率 RoR ·
      <span style="font-size:12px;color:var(--ink-2);font-weight:400">
        {detail.ror_method.window_s}s 末端窗口、对实测点最小二乘拟合，单位 °C/min
      </span>
    </h2>
    <EChart option={rorOpt} height="240px" />
    <p style="font-size:11.5px;color:var(--ink-2);margin:6px 0 0">
      窗口定义：[t − {detail.ror_method.window_s}s, t] 内仅使用实测锚点
      （≥ {detail.ror_method.min_measured_anchors} 个、覆盖 ≥ {(detail.ror_method.min_window_coverage * 100).toFixed(0)}% 窗口）；
      插值点不参与拟合；缺口复出首点锚点不足，温升率为空（图中断线）。
    </p>
  </div>

  <MetricsPanel metrics={detail.metrics} />

  <EventPanel
    events={detail.events}
    suggestion={detail.turn_suggestion}
    {loading}
    error={formErr}
    message={formMsg}
    on:submit={onSubmit}
    on:accept-suggestion={onAcceptSuggestion}
    on:revert={onRevert}
  />
{/if}
