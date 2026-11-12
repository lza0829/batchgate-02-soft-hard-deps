<script setup>
import { computed, onMounted, ref } from 'vue'
import { getJSON } from '../api'

const stats = ref(null)
const jobs = ref([])
const err = ref('')

const hardEdges = computed(() =>
  jobs.value.reduce((n, j) => n + (j.dependencies || []).filter((e) => e.kind === 'hard').length, 0),
)
const softEdges = computed(() =>
  jobs.value.reduce((n, j) => n + (j.dependencies || []).filter((e) => e.kind === 'soft').length, 0),
)

onMounted(async () => {
  try {
    stats.value = await getJSON('/api/dashboard')
    jobs.value = await getJSON('/api/jobs')
  } catch (e) {
    err.value = String(e.message || e)
  }
})
</script>

<template>
  <div class="page">
    <h1>总览</h1>
    <p class="muted">离线作业依赖编排：作业数、编排次数、依赖分流与已写出水位的作业。</p>
    <p v-if="err" class="tag danger">{{ err }}</p>
    <div class="panel" v-if="stats">
      <p>作业 {{ stats.job_count }}（启用 {{ stats.enabled_jobs }}）</p>
      <p>编排 {{ stats.orchestration_count }} · 尝试 {{ stats.attempt_count }}</p>
      <p>已有水位的作业 {{ stats.watermarked_jobs }}</p>
      <p>依赖边：硬 {{ hardEdges }} 条 · 软 {{ softEdges }} 条</p>
    </div>
  </div>
</template>
