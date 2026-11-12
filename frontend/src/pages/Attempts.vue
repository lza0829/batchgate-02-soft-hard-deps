<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { getJSON } from '../api'

const route = useRoute()
const orchId = ref(null)
const orchList = ref([])
const rows = ref([])
const err = ref('')
const reconcile = ref(null)

const STATUS_LABELS = {
  success: '成功',
  failed: '失败',
  skipped_hard: '硬阻断跳过',
  skipped_dep: '硬阻断跳过（旧）',
  degraded: '软降级执行',
}

function statusLabel(s) {
  return STATUS_LABELS[s] || s
}

function statusClass(s) {
  if (s === 'success') return 'ok'
  if (s === 'failed') return 'danger'
  if (s === 'degraded') return 'warn'
  return 'block'
}

const counts = computed(() => {
  const c = { success: 0, failed: 0, skipped_hard: 0, degraded: 0, other: 0 }
  for (const r of rows.value) {
    if (r.status === 'success') c.success += 1
    else if (r.status === 'failed') c.failed += 1
    else if (r.status === 'skipped_hard' || r.status === 'skipped_dep') c.skipped_hard += 1
    else if (r.status === 'degraded') c.degraded += 1
    else c.other += 1
  }
  return c
})

async function load() {
  err.value = ''
  reconcile.value = null
  try {
    const q = orchId.value != null ? `?orchestration_id=${orchId.value}` : ''
    rows.value = await getJSON(`/api/attempts${q}`)
    if (orchId.value != null) {
      reconcile.value = await getJSON(`/api/orchestrations/${orchId.value}/reconcile`)
    }
  } catch (e) {
    err.value = String(e.message || e)
  }
}

onMounted(async () => {
  try {
    orchList.value = await getJSON('/api/orchestrations')
    const q = Number(route.query.orchestration_id)
    if (q) orchId.value = q
    await load()
  } catch (e) {
    err.value = String(e.message || e)
  }
})

watch(orchId, load)
</script>

<template>
  <div class="page">
    <h1>尝试记录</h1>
    <p class="muted">
      每条尝试分属一个桶：success / failed / skipped_hard（硬阻断）/ degraded（软降级执行）。
    </p>
    <p v-if="err" class="tag danger">{{ err }}</p>
    <div class="panel">
      <label>
        编排
        <select v-model.number="orchId">
          <option :value="null">全部</option>
          <option v-for="o in orchList" :key="o.id" :value="o.id">#{{ o.id }} · {{ o.status }}</option>
        </select>
      </label>
      <span class="muted" style="margin-left: 0.75rem">共 {{ rows.length }} 条</span>
    </div>

    <div class="panel">
      <table>
        <thead>
          <tr>
            <th>成功</th><th>失败</th><th>硬阻断跳过</th><th>软降级执行</th><th>合计</th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <td class="mono">{{ counts.success }}</td>
            <td class="mono">{{ counts.failed }}</td>
            <td class="mono">{{ counts.skipped_hard }}</td>
            <td class="mono">{{ counts.degraded }}</td>
            <td class="mono">{{ rows.length }}</td>
          </tr>
        </tbody>
      </table>
      <p v-if="reconcile" style="margin-top: 0.6rem">
        <span class="tag" :class="reconcile.balanced ? 'ok' : 'danger'">
          {{ reconcile.balanced ? '与报告逐项一致' : '与报告不一致' }}
        </span>
        <span v-if="reconcile.mismatches?.length" class="mono muted" style="margin-left: 0.6rem">
          {{ JSON.stringify(reconcile.mismatches) }}
        </span>
      </p>
    </div>

    <div class="panel">
      <table>
        <thead>
          <tr><th>ID</th><th>编排</th><th>作业</th><th>次</th><th>状态</th><th>分流原因</th><th>详情</th></tr>
        </thead>
        <tbody>
          <tr v-for="a in rows" :key="a.id">
            <td>{{ a.id }}</td>
            <td>{{ a.orchestration_id }}</td>
            <td class="mono">{{ a.job_name }}</td>
            <td>{{ a.attempt_no }}</td>
            <td>
              <span class="tag" :class="statusClass(a.status)">{{ statusLabel(a.status) }}</span>
            </td>
            <td class="muted">{{ a.detail?.reason || a.detail?.error || '—' }}</td>
            <td class="mono detail">{{ JSON.stringify(a.detail) }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<style scoped>
.tag.block { background: #e2e2e2; color: #4a4a4a; }
.detail {
  max-width: 26rem;
  overflow-wrap: anywhere;
  white-space: normal;
}
</style>
