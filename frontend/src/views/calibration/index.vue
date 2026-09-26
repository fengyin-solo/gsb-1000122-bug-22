<template>
  <section class="page" data-module="calibration">
    <header class="page-head">
      <div>
        <h2>校准记录管理</h2>
        <p class="page-desc">维护校准记录单，围绕记录编号、仪器编号、校准机构、校准日期做登记、筛选与状态流转。</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="openCreate">登记校准记录单</button>
        <button class="btn" type="button" :disabled="importing" @click="openImport">
          {{ importing ? '导入中…' : '导入校准记录' }}
        </button>
        <button class="btn" type="button" @click="exportRows">导出校准记录清单</button>
        <input
          ref="fileInput"
          type="file"
          accept=".csv,.json"
          class="visually-hidden"
          @change="onFileChange"
        />
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in stats" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <form class="filter-bar" @submit.prevent="reload">
      <label v-for="field in filterFields" :key="field" class="filter-item">
        <span>{{ field }}</span>
        <input v-model="filters[field]" :placeholder="`按${field}检索`" />
      </label>
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
    </form>

    <div v-if="importResult" class="import-panel" :class="{ failed: !importResult.ok }">
      <header class="import-head">
        <strong>{{ importResult.message }}</strong>
        <button class="link" type="button" @click="importResult = null">收起</button>
      </header>
      <ul v-if="importResult.results.length" class="import-rows">
        <li
          v-for="item in importResult.results"
          :key="item.row"
          class="import-row"
          :data-result="item.result"
        >
          <span class="import-row-no">第 {{ item.row }} 行</span>
          <span class="import-row-key">{{ item.key || '—' }}</span>
          <span class="import-row-result">{{ item.result }}</span>
          <span class="import-row-msg">{{ item.message }}</span>
        </li>
      </ul>
    </div>

    <table class="data-table">
      <thead>
        <tr>
          <th v-for="column in columns" :key="column">{{ column }}</th>
          <th>可执行动作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="String(row.id)">
          <td v-for="column in columns" :key="column">{{ row[column] ?? '—' }}</td>
          <td class="row-actions">
            <button
              v-for="action in actions"
              :key="action"
              class="link"
              type="button"
              @click="runAction(action, row)"
            >
              {{ action }}
            </button>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 1" class="empty-state">暂无校准记录数据，可先登记校准记录单</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条校准记录记录</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'

import { request } from '@/api/client'

type Row = Record<string, string | number | null>
type StatCard = { label: string; value: number }
type ImportRowResult = { row: number; key: string; result: string; message: string }
type ImportResult = {
  ok: boolean
  message: string
  summary: Record<string, number>
  results: ImportRowResult[]
}

const ENDPOINT = '/api/calibration'
const columns = ["记录编号", "仪器编号", "校准机构", "校准日期", "校准结果", "偏差值", "校准证书号", "记录状态"]
const actions = ["执行校准", "标记合格", "标记不合格"]
const statuses = ["待校准", "校准中", "已合格", "不合格"]

const rows = ref<Row[]>([])
const total = ref(0)
const errorMessage = ref('')
const filters = ref<Record<string, string>>({})
const filterFields = columns.slice(0, 3)
const stats = ref<StatCard[]>([
  { label: '待校准记录', value: 0 },
  { label: '合格记录', value: 0 },
  { label: '不合格记录', value: 0 },
])
const fileInput = ref<HTMLInputElement | null>(null)
const importing = ref(false)
const importResult = ref<ImportResult | null>(null)

function resetFilters() {
  filters.value = {}
  void reload()
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

function openCreate() {
  errorMessage.value = '校准记录单登记入口尚未接入审批流'
}

function openImport() {
  errorMessage.value = ''
  fileInput.value?.click()
}

async function onFileChange(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  // 允许中断后重选同一个文件再次导入
  input.value = ''
  if (!file || importing.value) {
    return
  }
  importing.value = true
  errorMessage.value = ''
  try {
    const form = new FormData()
    form.append('file', file)
    const response = await request(`${ENDPOINT}/import`, { method: 'POST', body: form })
    const payload = (await response.json()) as ImportResult
    importResult.value = payload
    if (!response.ok || !payload.ok) {
      errorMessage.value = payload.message || '校准记录导入失败，请检查文件后重试'
    }
    // 无论成败都刷新列表与指标，保证页面和已入库的数据对齐
    await Promise.all([reload(), loadStats()])
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '校准记录导入失败'
  } finally {
    importing.value = false
  }
}

async function runAction(action: string, row: Row) {
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ values: { action } }),
    })
    const payload = await response.json()
    if (!response.ok || !payload.ok) {
      throw new Error(payload.message || '校准记录动作未生效，请稍后重试')
    }
    await Promise.all([reload(), loadStats()])
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '校准记录操作失败'
  }
}

async function loadStats() {
  try {
    const response = await request(`${ENDPOINT}/stats`)
    if (!response.ok) {
      return
    }
    const payload = await response.json()
    stats.value = payload.cards ?? stats.value
  } catch {
    // 指标卡读取失败不打断列表展示
  }
}

async function reload() {
  errorMessage.value = ''
  const query = new URLSearchParams(filters.value as Record<string, string>).toString()
  try {
    const response = await request(`${ENDPOINT}?${query}`)
    if (!response.ok) {
      throw new Error('校准记录单列表读取失败')
    }
    const payload = await response.json()
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '校准记录列表读取失败'
  }
}

onMounted(() => {
  void reload()
  void loadStats()
})
</script>

<style scoped>
.visually-hidden {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip: rect(0 0 0 0);
}
.import-panel {
  background: #fff;
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 10px 12px;
  margin-bottom: 12px;
  font-size: 13px;
}
.import-panel.failed {
  border-color: #f04438;
}
.import-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
}
.import-rows {
  list-style: none;
  margin: 8px 0 0;
  padding: 8px 0 0;
  border-top: 1px dashed var(--border);
  max-height: 220px;
  overflow: auto;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.import-row {
  display: flex;
  gap: 10px;
  align-items: baseline;
}
.import-row-no {
  color: var(--muted);
  min-width: 56px;
}
.import-row-key {
  min-width: 110px;
  font-weight: 600;
}
.import-row-result {
  min-width: 48px;
}
.import-row[data-result='失败'] .import-row-result,
.import-row[data-result='失败'] .import-row-msg {
  color: #b42318;
}
.import-row[data-result='重复'] .import-row-result {
  color: #b54708;
}
.import-row[data-result='新建'] .import-row-result {
  color: #067647;
}
.import-row[data-result='更新'] .import-row-result {
  color: var(--brand);
}
.import-row[data-result='空行'] .import-row-result,
.import-row[data-result='未变化'] .import-row-result {
  color: var(--muted);
}
</style>
