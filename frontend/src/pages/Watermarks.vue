<script setup>
import { computed, onMounted, ref } from 'vue'
import { getJSON } from '../api'

const rows = ref([])
const err = ref('')

async function load() {
  err.value = ''
  try {
    rows.value = await getJSON('/api/watermarks')
  } catch (e) {
    err.value = String(e.message || e)
  }
}

// Only jobs that actually executed successfully have a watermark. Soft-degraded
// executions are intentionally absent here; they are visible as `degraded` in
// the attempt list instead.
const promoted = computed(() => rows.value.filter((w) => w.watermark_ts))

onMounted(load)
</script>

<template>
  <div class="page">
    <h1>产出水位</h1>
    <p class="muted">
      只列出真正执行成功并推进了水位的作业；被硬阻断或软降级的执行不会出现在这里。
    </p>
    <p v-if="err" class="tag danger">{{ err }}</p>
    <div class="panel">
      <p class="muted">已有水位 {{ promoted.length }} / {{ rows.length }} 个作业</p>
      <table>
        <thead><tr><th>作业</th><th>watermark</th><th>行数</th><th>更新</th></tr></thead>
        <tbody>
          <tr v-for="w in promoted" :key="w.job_id">
            <td class="mono">{{ w.job_name }}</td>
            <td class="mono">{{ w.watermark_ts }}</td>
            <td>{{ w.artifact_rows }}</td>
            <td class="mono">{{ w.updated_at || '—' }}</td>
          </tr>
          <tr v-if="!promoted.length">
            <td colspan="4" class="muted">暂无成功水位</td>
          </tr>
        </tbody>
      </table>
    </div>
    <div class="panel">
      <h3>尚未推进水位的作业</h3>
      <p class="muted" v-if="!rows.length - promoted.length" style="margin: 0">全部作业均已有水位。</p>
      <ul v-else>
        <li v-for="w in rows.filter((x) => !x.watermark_ts)" :key="w.job_id" class="mono">
          {{ w.job_name }} <span class="muted">（未成功执行或本次被阻断/降级）</span>
        </li>
      </ul>
    </div>
  </div>
</template>
