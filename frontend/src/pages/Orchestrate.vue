<script setup>
import { computed, onMounted, ref } from 'vue'
import { getJSON, postJSON } from '../api'

const history = ref([])
const last = ref(null)
const busy = ref(false)
const err = ref('')

async function refresh() {
  history.value = await getJSON('/api/orchestrations')
}

async function runOnce() {
  err.value = ''
  busy.value = true
  try {
    last.value = await postJSON('/api/orchestrations')
    await refresh()
  } catch (e) {
    err.value = String(e.message || e)
  } finally {
    busy.value = false
  }
}

const checks = computed(() => {
  const report = last.value?.report
  if (!report) return []
  const sum =
    (report.succeeded || 0) +
    (report.failed || 0) +
    (report.hard_skipped || 0) +
    (report.soft_degraded || 0)
  return [
    { label: '成功', value: report.succeeded || 0 },
    { label: '失败', value: report.failed || 0 },
    { label: '硬阻断跳过', value: report.hard_skipped || 0 },
    { label: '软降级执行', value: report.soft_degraded || 0 },
    { label: '尝试记录', value: report.attempt_count || 0 },
    { label: '分项合计', value: sum },
  ]
})

const balanced = computed(() => {
  const report = last.value?.report
  if (!report) return true
  return (
    report.succeeded + report.failed + report.hard_skipped + report.soft_degraded ===
    report.attempt_count
  )
})

onMounted(async () => {
  try {
    await refresh()
  } catch (e) {
    err.value = String(e.message || e)
  }
})
</script>

<template>
  <div class="page">
    <h1>编排台</h1>
    <p class="muted">
      触发一次全图编排：硬依赖未就绪时下游记 <code>skipped_hard</code>；软依赖未就绪时下游照常执行并记 <code>degraded</code>。
    </p>
    <div class="panel">
      <button :disabled="busy" @click="runOnce">{{ busy ? '编排中…' : '执行编排' }}</button>
    </div>
    <p v-if="err" class="tag danger">{{ err }}</p>
    <div class="panel" v-if="last">
      <h3>最近一次报告</h3>
      <p>
        #{{ last.id }} · <span class="tag ok">{{ last.status }}</span>
      </p>
      <table>
        <thead><tr><th>指标</th><th>数值</th></tr></thead>
        <tbody>
          <tr v-for="c in checks" :key="c.label">
            <td>{{ c.label }}</td>
            <td class="mono">{{ c.value }}</td>
          </tr>
        </tbody>
      </table>
      <p style="margin-top: 0.6rem">
        <span class="tag" :class="balanced ? 'ok' : 'danger'">
          {{ balanced ? '报告与尝试记录对得上' : '报告与尝试记录不一致' }}
        </span>
        <span class="muted" style="margin-left: 0.6rem">
          watermarked_in_run={{ last.report?.watermarked_in_run }} · layers={{ last.report?.layer_count }}
        </span>
      </p>
      <p>
        <router-link :to="{ path: '/attempts', query: { orchestration_id: last.id } }">查看本次尝试 →</router-link>
        · <router-link :to="{ path: '/attempts', query: { orchestration_id: last.id } }">降级标记 →</router-link>
        · <router-link to="/watermarks">产出水位 →</router-link>
      </p>
    </div>
    <div class="panel">
      <h3>历史编排</h3>
      <table>
        <thead>
          <tr><th>ID</th><th>状态</th><th>成功</th><th>失败</th><th>硬跳过</th><th>软降级</th><th>开始</th></tr>
        </thead>
        <tbody>
          <tr v-for="o in history" :key="o.id">
            <td>{{ o.id }}</td>
            <td>{{ o.status }}</td>
            <td>{{ o.report?.succeeded ?? '—' }}</td>
            <td>{{ o.report?.failed ?? '—' }}</td>
            <td>{{ o.report?.hard_skipped ?? '—' }}</td>
            <td>{{ o.report?.soft_degraded ?? '—' }}</td>
            <td class="mono">{{ o.started_at }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>
