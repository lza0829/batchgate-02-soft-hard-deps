<script setup>
import { computed, onMounted, ref } from 'vue'
import { getJSON, patchJSON, putJSON } from '../api'

const rows = ref([])
const allNames = ref([])
const fixtures = ref([])
const msg = ref('')
const err = ref('')

// Local editable copy of each job's dependency edges, keyed by job id.
const drafts = ref({})

function cloneEdges(edges) {
  return (edges || []).map((e) => ({ name: e.name, kind: e.kind }))
}

async function refresh() {
  rows.value = await getJSON('/api/jobs')
  fixtures.value = await getJSON('/api/fixtures')
  allNames.value = rows.value.map((j) => j.name)
  const next = {}
  for (const j of rows.value) next[j.id] = cloneEdges(j.dependencies)
  drafts.value = next
}

async function saveFixture(job) {
  err.value = ''
  msg.value = ''
  try {
    await patchJSON(`/api/jobs/${job.id}/fixture`, { fixture_path: job.fixture_path })
    msg.value = `已保存 ${job.name} 的夹具`
    await refresh()
  } catch (e) {
    err.value = String(e.message || e)
  }
}

function addEdge(job) {
  const candidates = allNames.value.filter(
    (n) => n !== job.name && !drafts.value[job.id].some((e) => e.name === n),
  )
  if (!candidates.length) {
    err.value = '没有可添加的上游作业'
    return
  }
  err.value = ''
  drafts.value[job.id].push({ name: candidates[0], kind: 'hard' })
}

function removeEdge(job, index) {
  drafts.value[job.id].splice(index, 1)
}

async function saveDependencies(job) {
  err.value = ''
  msg.value = ''
  try {
    const payload = { dependencies: drafts.value[job.id].map((e) => ({ name: e.name, kind: e.kind })) }
    const updated = await putJSON(`/api/jobs/${job.id}/dependencies`, payload)
    msg.value = `已保存 ${job.name} 的依赖边（${updated.dependencies.length} 条）`
    await refresh()
  } catch (e) {
    err.value = String(e.message || e)
  }
}

async function saveAttempts(job) {
  err.value = ''
  msg.value = ''
  try {
    await patchJSON(`/api/jobs/${job.id}/max-attempts`, {
      max_attempts: Number(job.max_attempts) || 1,
    })
    msg.value = `已保存 ${job.name} 的 max_attempts`
    await refresh()
  } catch (e) {
    err.value = String(e.message || e)
  }
}

async function toggleEnabled(job) {
  err.value = ''
  msg.value = ''
  try {
    await patchJSON(`/api/jobs/${job.id}/enabled`, { enabled: !job.enabled })
    await refresh()
  } catch (e) {
    err.value = String(e.message || e)
  }
}

const hardCount = computed(() =>
  rows.value.reduce((n, j) => n + (j.dependencies || []).filter((e) => e.kind === 'hard').length, 0),
)
const softCount = computed(() =>
  rows.value.reduce((n, j) => n + (j.dependencies || []).filter((e) => e.kind === 'soft').length, 0),
)

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
    <h1>作业</h1>
    <p class="muted">
      为上游依赖配置 <strong>硬</strong> 或 <strong>软</strong> 边：硬边未就绪时下游整段阻断；软边未就绪时下游降级执行并留标记。
    </p>
    <p v-if="err" class="tag danger">{{ err }}</p>
    <p v-if="msg" class="tag ok">{{ msg }}</p>
    <div class="panel">
      <p class="muted">当前依赖边：硬 {{ hardCount }} 条 · 软 {{ softCount }} 条</p>
      <table>
        <thead>
          <tr>
            <th>ID</th>
            <th>名称</th>
            <th>依赖边（上游 / 类型）</th>
            <th>max_attempts</th>
            <th>启用</th>
            <th>夹具</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="j in rows" :key="j.id">
            <td>{{ j.id }}</td>
            <td class="mono">{{ j.name }}</td>
            <td>
              <div v-if="!drafts[j.id]?.length" class="muted">无依赖</div>
              <div v-for="(edge, idx) in drafts[j.id]" :key="`${j.id}-${idx}`" class="edge-row">
                <select v-model="edge.name">
                  <option v-for="n in allNames.filter((x) => x !== j.name)" :key="n" :value="n">{{ n }}</option>
                </select>
                <select v-model="edge.kind">
                  <option value="hard">硬</option>
                  <option value="soft">软</option>
                </select>
                <span class="tag" :class="edge.kind === 'hard' ? 'danger' : 'warn'">
                  {{ edge.kind === 'hard' ? '阻断' : '降级' }}
                </span>
                <button class="secondary" @click="removeEdge(j, idx)">移除</button>
              </div>
              <div style="margin-top: 0.35rem">
                <button class="secondary" @click="addEdge(j)">+ 添加依赖</button>
                <button style="margin-left: 0.35rem" @click="saveDependencies(j)">保存依赖</button>
              </div>
            </td>
            <td><input type="number" min="1" max="10" v-model.number="j.max_attempts" style="width: 4.5rem" /></td>
            <td>
              <span class="tag" :class="j.enabled ? 'ok' : ''">{{ j.enabled ? '启用' : '停用' }}</span>
              <button class="secondary" style="margin-left: 0.35rem" @click="toggleEnabled(j)">
                {{ j.enabled ? '停用' : '启用' }}
              </button>
            </td>
            <td>
              <select v-model="j.fixture_path">
                <option v-for="f in fixtures" :key="f" :value="f">{{ f }}</option>
              </select>
              <button class="secondary" style="margin-left: 0.35rem" @click="saveFixture(j)">保存夹具</button>
            </td>
            <td><button class="secondary" @click="saveAttempts(j)">保存次数</button></td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<style scoped>
.edge-row {
  display: flex;
  align-items: center;
  gap: 0.3rem;
  margin-bottom: 0.3rem;
  flex-wrap: wrap;
}
</style>
