<script>
  import { createEventDispatcher } from 'svelte';
  import { EVENT_LABELS, fmtTime } from './format.js';

  export let events = [];
  export let suggestion = null;
  export let loading = false;
  export let error = '';
  export let message = '';

  const dispatch = createEventDispatcher();

  let form = {
    event_type: 'turn',
    mm: '1',
    ss: '20',
    value: '',
    operator: '',
    note: '',
  };

  const ANCHORS = ['charge', 'turn', 'first_crack', 'drop'];

  function submit() {
    const event_time = Number(form.mm) * 60 + Number(form.ss || 0);
    dispatch('submit', {
      event_type: form.event_type,
      event_time,
      value: form.value === '' ? null : Number(form.value),
      operator: form.operator,
      note: form.note,
    });
  }

  function revert(e) {
    const op = prompt(`恢复历史版本需要留名。请输入操作员姓名：`, form.operator);
    if (op && op.trim()) dispatch('revert', { id: e.id, operator: op.trim() });
  }
</script>

<div class="panel">
  <h2>操作事件与人工修正</h2>
  <p style="font-size:12px;color:var(--ink-2);margin:0 0 8px">
    锚点（下豆/回温点/一爆/出锅）修正后，旧记录保留为历史并标记来源；
    风门与人工标记为追加记录。
  </p>

  {#if suggestion}
    <div class="disclaimer" style="margin-bottom:10px">
      算法建议回温点：<b>{fmtTime(suggestion.t_s)}</b>
      （豆温 {suggestion.bean_temp_c}°C，基于
      <code class="method">{suggestion.method.detector}</code>，
      平滑窗口 {suggestion.method.smooth_window_s}s）——仅为建议，需操作员确认：
      <button
        style="margin-left:8px"
        disabled={loading}
        on:click={() => dispatch('accept-suggestion', suggestion)}
      >确认采用</button>
    </div>
  {/if}

  <table class="events">
    <thead>
      <tr><th>事件</th><th>时间</th><th>数值</th><th>来源 / 操作员</th><th>备注与修正链</th><th></th></tr>
    </thead>
    <tbody>
      {#each events as e (e.id)}
        <tr class:hist={!e.is_current}>
          <td>{EVENT_LABELS[e.event_type] || e.event_type}</td>
          <td>{fmtTime(e.event_time)}</td>
          <td>{e.value == null ? '—' : e.value}</td>
          <td>
            <span class="pill {e.source}">{e.source === 'auto' ? '合成预置' : '人工'}</span>
            <div>{e.operator || '—'}</div>
          </td>
          <td>
            {e.note}
            {#if e.supersedes_id}
              <div class="sub">取代了事件 #{e.supersedes_id}
                {#if e.method?.previous_source}（原来源：{e.method.previous_source}，原时间 {fmtTime(e.method.previous_time_s)}）{/if}
              </div>
            {/if}
          </td>
          <td>
            {#if !e.is_current && ANCHORS.includes(e.event_type)}
              <button class="ghost" disabled={loading} on:click={() => revert(e)}>恢复</button>
            {/if}
          </td>
        </tr>
      {/each}
    </tbody>
  </table>

  <h3>新增 / 修正事件</h3>
  <div class="form-row">
    <select bind:value={form.event_type}>
      {#each Object.entries(EVENT_LABELS) as [val, label]}
        <option value={val}>{label}</option>
      {/each}
    </select>
    <span>
      <input type="number" min="0" bind:value={form.mm} style="width:58px" /> 分
      <input type="number" min="0" max="59" bind:value={form.ss} style="width:58px" /> 秒
    </span>
    {#if form.event_type === 'damper'}
      <input type="number" min="0" max="100" placeholder="风门 %" bind:value={form.value} style="width:90px" />
    {/if}
    <input placeholder="操作员（必填）" bind:value={form.operator} style="width:130px" />
    <input placeholder="备注" bind:value={form.note} style="flex:1;min-width:160px" />
    <button disabled={loading} on:click={submit}>提交修正</button>
  </div>
  {#if error}<div class="error">{error}</div>{/if}
  {#if message}<div class="ok-msg">{message}</div>{/if}
</div>
