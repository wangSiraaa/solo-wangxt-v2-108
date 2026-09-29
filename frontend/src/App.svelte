<script>
  import { onMount } from 'svelte';
  import { api } from './api.js';
  import BatchView from './views/BatchView.svelte';
  import CompareView from './views/CompareView.svelte';

  let batches = [];
  let loadErr = '';
  let route = location.hash.replace('#/', '') || 'batch:1';

  function onHash() {
    route = location.hash.replace('#/', '') || 'batch:1';
  }
  onMount(() => {
    window.addEventListener('hashchange', onHash);
    api.listBatches()
      .then((bs) => {
        batches = bs;
        if (route.startsWith('batch:')) {
          const id = Number(route.split(':')[1]);
          if (!batches.some((b) => b.id === id)) route = `batch:${batches[0]?.id ?? ''}`;
        }
      })
      .catch((e) => (loadErr = e.message));
  });

  $: view = route.split(':')[0];
  $: batchId = view === 'batch' ? Number(route.split(':')[1]) : null;
</script>

<header class="topbar">
  <h1>☕ RoastLog 烘焙批次过程记录</h1>
  <nav>
    <a href="#/batch:{batchId ?? 1}" class:active={view === 'batch'}>单批次</a>
    <a href="#/compare" class:active={view === 'compare'}>双批次对比</a>
  </nav>
  <span class="sub">豆温 · 环境温度 · 操作事件 · 合成数据（未连接真实烘焙机）</span>
</header>

{#if loadErr}
  <div class="layout"><div class="panel error">无法加载批次：{loadErr}（请确认后端已启动）</div></div>
{:else}
  <div class="layout">
    <aside class="sidebar">
      <h2>批次列表</h2>
      {#each batches as b}
        <div
          class="batch-item"
          class:active={view === 'batch' && batchId === b.id}
          on:click={() => (location.hash = `#/batch:${b.id}`)}
          on:keydown={() => {}}
          role="button"
          tabindex="0"
        >
          <div class="code">{b.code}</div>
          <div class="meta">
            {b.profile_name}<br />
            {b.roast_date} · {b.n_samples} 采样 · {b.n_gaps} 失联段
          </div>
        </div>
      {/each}
      <h2 style="margin-top:16px">数据说明</h2>
      <p style="font-size:11.5px;color:var(--ink-2);line-height:1.6">
        采样为非均匀间隔，含测量噪声、探针短暂失联与个别跳变读数。<br /><br />
        <b>实线</b>=实测；<b>虚线</b>=短缺口线性插值（非实测）；
        <b>灰带</b>=长失联留空。<br /><br />
        温升率使用可配置的末端窗口回归，调整平滑/窗口参数不会修改任何原始温度。
      </p>
    </aside>

    <main class="main">
      {#if view === 'batch' && batchId}
        <BatchView {batchId} key={batchId} />
      {:else if view === 'compare'}
        <CompareView {batches} />
      {/if}
    </main>
  </div>
{/if}
