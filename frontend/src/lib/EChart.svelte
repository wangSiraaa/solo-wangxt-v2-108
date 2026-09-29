<script>
  import { onMount, onDestroy } from 'svelte';
  import * as echarts from 'echarts';

  export let option;
  export let height = '460px';

  let el;
  let chart;

  onMount(() => {
    chart = echarts.init(el);
    chart.setOption(option);
    const ro = new ResizeObserver(() => chart.resize());
    ro.observe(el);
    return () => {
      ro.disconnect();
      chart.dispose();
    };
  });

  $: if (chart) {
    chart.setOption(option, true);
  }
</script>

<div class="chart" bind:this={el} style:height></div>
