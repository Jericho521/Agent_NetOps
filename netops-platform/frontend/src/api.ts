/**
 * API 封装 - axios 实例 + JWT Token 管理
 */

const API_BASE = '/api'

export interface LoginRequest {
  username: string
  password: string
}

export interface UserInfo {
  id: string
  username: string
  role: string
}

export interface Device {
  id: string
  name: string
  sys_name: string | null
  device_type: 'single' | 'stack' | 'mlag' | 'cluster'
  ip: string
  snmp_version: number
  snmp_port: number
  snmp_user: string | null
  vendor: string | null
  model: string | null
  role: string | null
  region: string | null
  region_id: string | null
  sub_region_id: string | null
  region_name: string | null
  sub_region_name: string | null
  poll_interval: number
  adapter: string
  ssh_port: number
  enabled: boolean
  status: string
  last_seen_at: string | null
  created_at: string | null
}

export interface AlertRule {
  id: string
  name: string
  device_id: string | null
  metric_name: string
  operator: string
  threshold: number
  duration_seconds: number
  severity: number
  critical_threshold: number | null
  enabled: boolean
  created_at: string | null
}

export interface AlertItem {
  id: string
  rule_id: string
  device_id: string
  status: string
  severity: number | null  // 离线/异常告警为 null（不进 P 级别体系）
  category: string  // threshold / offline / error
  message: string
  value: number | null
  fired_at: string | null
  acknowledged_at: string | null
  resolved_at: string | null
}

// Token 存储
const TOKEN_KEY = 'netops_token'
const USER_KEY = 'netops_user'

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY)
}

export function getUser(): UserInfo | null {
  const raw = localStorage.getItem(USER_KEY)
  return raw ? JSON.parse(raw) : null
}

export function setAuth(token: string, user: UserInfo): void {
  localStorage.setItem(TOKEN_KEY, token)
  localStorage.setItem(USER_KEY, JSON.stringify(user))
}

export function clearAuth(): void {
  localStorage.removeItem(TOKEN_KEY)
  localStorage.removeItem(USER_KEY)
}

// axios 实例
import axios from 'axios'

const api = axios.create({
  baseURL: API_BASE,
  timeout: 30000,
})

// 请求拦截器：自动附加 Token
api.interceptors.request.use((config) => {
  const token = getToken()
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

// 响应拦截器：401 自动跳转登录
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      clearAuth()
      window.location.href = '/login'
    }
    return Promise.reject(error)
  },
)

/**
 * 流式测试连通性（SSE over fetch）。
 * onStage 回调接收每个阶段的进度对象 {stage,status,message,progress,detail}
 */
export async function testConnectivityStream(
  id: string,
  onStage: (stage: any) => void,
): Promise<void> {
  const token = getToken()
  const resp = await fetch(`${API_BASE}/devices/${id}/test-connectivity-stream`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}` },
  })
  if (!resp.ok || !resp.body) {
    throw new Error(`HTTP ${resp.status}`)
  }
  const reader = resp.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    // 按 SSE 分隔符切分
    const parts = buffer.split('\n\n')
    buffer = parts.pop() || ''
    for (const part of parts) {
      const line = part.trim()
      if (!line.startsWith('data:')) continue
      const data = line.slice(5).trim()
      if (data === '__DONE__') return
      try {
        onStage(JSON.parse(data))
      } catch { /* ignore */ }
    }
  }
}

// ========== 认证 API ==========
export async function login(username: string, password: string) {
  const resp = await api.post('/auth/login', { username, password })
  const { access_token, user_info } = resp.data
  setAuth(access_token, user_info)
  return user_info
}

export async function getMe() {
  const resp = await api.get('/auth/me')
  return resp.data as UserInfo
}

// ========== 设备 API ==========
export async function fetchDevices(params?: {
  page?: number
  page_size?: number
  vendor?: string
  role?: string
  enabled?: boolean
  search?: string
  region_id?: string
  sub_region_id?: string
}) {
  const resp = await api.get('/devices', { params })
  return resp.data as { total: number; items: Device[] }
}

export async function fetchDevice(id: string) {
  const resp = await api.get(`/devices/${id}`)
  return resp.data as Device
}

export async function createDevice(data: any) {
  const resp = await api.post('/devices', data)
  return resp.data as Device
}

export async function updateDevice(id: string, data: any) {
  const resp = await api.put(`/devices/${id}`, data)
  return resp.data as Device
}

export async function deleteDevice(id: string) {
  const resp = await api.delete(`/devices/${id}`)
  return resp.data
}

export async function importDevicesCSV(file: File) {
  const formData = new FormData()
  formData.append('file', file)
  const resp = await api.post('/devices/import/csv', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
  return resp.data
}

export async function testConnectivity(deviceId: string) {
  const resp = await api.post(`/devices/${deviceId}/test-connectivity`)
  return resp.data
}

// ========== 指标 API ==========
export interface MetricDataPoint {
  timestamp: number
  value: number | null
}

export interface MetricSeries {
  metric: Record<string, string>
  values: MetricDataPoint[]
}

export interface MetricsResponse {
  metric_name: string
  data: MetricSeries[]
  error?: string
}

export async function fetchMetrics(
  deviceId: string,
  metricNames: string = 'snmp_cpu_usage_percent,snmp_memory_usage_percent',
  rangeHours: number = 1,
  stepSeconds: number = 60,
) {
  const resp = await api.get('/metrics/query', {
    params: {
      device_id: deviceId,
      metric_names: metricNames,
      range_hours: rangeHours,
      step_seconds: stepSeconds,
    },
  })
  return resp.data as MetricsResponse[]
}

// ========== 告警 API ==========
export async function fetchAlertRules(enabledOnly = false) {
  const resp = await api.get('/alerts/rules', { params: { enabled_only: enabledOnly } })
  return resp.data as AlertRule[]
}

export async function createAlertRule(data: any) {
  const resp = await api.post('/alerts/rules', data)
  return resp.data as AlertRule
}

export async function deleteAlertRule(ruleId: string) {
  const resp = await api.delete(`/alerts/rules/${ruleId}`)
  return resp.data
}

export async function updateAlertRule(ruleId: string, data: any) {
  const resp = await api.put(`/alerts/rules/${ruleId}`, data)
  return resp.data as AlertRule
}

export async function resolveAlert(alertId: string, by: string) {
  const resp = await api.put(`/alerts/${alertId}/resolve`, { resolved_by: by })
  return resp.data
}

/** 设备概览统计（在线/离线/总数/告警数） */
export async function fetchOverview() {
  const resp = await api.get('/devices/overview')
  return resp.data as {
    total: number
    online: number
    offline: number
    warning: number
    total_alerts_active: number
  }
}

export interface ConfigBackup {
  id: string
  device_id: string
  revision: number
  content_hash: string
  captured_at: string
  captured_by: string
  change_summary: string | null
}

export async function fetchConfigBackups(deviceId: string) {
  const resp = await api.get(`/devices/${deviceId}/config/backups`)
  return resp.data as ConfigBackup[]
}

export async function createConfigBackup(deviceId: string) {
  const resp = await api.post(`/devices/${deviceId}/config/backups`)
  return resp.data as ConfigBackup
}

export async function fetchConfigBackupContent(deviceId: string, backupId: string) {
  const resp = await api.get(`/devices/${deviceId}/config/backups/${backupId}`)
  return resp.data as { id: string; revision: number; content: string; captured_at: string; captured_by: string }
}

export async function fetchConfigDiff(deviceId: string, backupId: string, compareWith?: string) {
  const params: any = {}
  if (compareWith) params.compare_with = compareWith
  const resp = await api.get(`/devices/${deviceId}/config/backups/${backupId}/diff`, { params })
  return resp.data as { old_revision: number; new_revision: number; diff: string }
}

export async function previewCurrentConfig(deviceId: string) {
  const resp = await api.post(`/devices/${deviceId}/config/preview`)
  return resp.data as { content: string }
}

export async function fetchAlerts(params?: {
  status?: string
  severity?: number
  device_id?: string
  page?: number
  page_size?: number
}) {
  const resp = await api.get('/alerts', { params })
  return resp.data as { total: number; items: AlertItem[] }
}

export async function acknowledgeAlert(alertId: string, by: string) {
  const resp = await api.put(`/alerts/${alertId}/acknowledge`, { acknowledged_by: by })
  return resp.data
}

// ========== AI 助手 API ==========
export async function chatWithAI(messages: { role: string; content: string }[], model?: string) {
  const resp = await api.post('/ai/chat', { messages, model })
  return resp.data as { content: string }
}

export async function analyzeWithAI(question?: string, model?: string) {
  const resp = await api.post('/ai/analyze', { question, model })
  return resp.data as { content: string }
}

export interface AIContextStats {
  devices_total: number
  devices_online: number
  devices_offline: number
  devices_error: number
  active_alerts: number
  recent_alerts: number
}

export async function getAIContext() {
  const resp = await api.get('/ai/context')
  return resp.data as AIContextStats
}

// ========== 报表中心 API ==========
export interface ReportInstance {
  id: string
  report_type: string
  created_at: string
  pdf_path?: string
  excel_path?: string
  status: string
  error_message?: string
}

export async function generateReport(report_type = 'daily', hours = 24) {
  const resp = await api.post('/reports/generate', { report_type, hours })
  return resp.data as ReportInstance
}

export async function listReportInstances(page = 1, page_size = 20) {
  const resp = await api.get('/reports/instances', { params: { page, page_size } })
  return resp.data as ReportInstance[]
}

export function downloadReportUrl(instanceId: string, format: 'pdf' | 'excel') {
  return `${api.defaults.baseURL}/reports/download/${instanceId}?format=${format}`
}

export async function deleteReport(instanceId: string) {
  await api.delete(`/reports/${instanceId}`)
}

// ========== 区域管理 API ==========
export interface SubRegionItem {
  id: string
  name: string
  description?: string
  sort_order: number
}

export interface RegionItem {
  id: string
  name: string
  description?: string
  sort_order: number
  sub_regions: SubRegionItem[]
}

export async function listRegions(): Promise<RegionItem[]> {
  const resp = await api.get('/regions')
  return resp.data as RegionItem[]
}

export async function createRegion(data: { name: string; description?: string; sort_order?: number }) {
  const resp = await api.post('/regions', data)
  return resp.data as RegionItem
}

export async function updateRegion(id: string, data: Partial<{ name: string; description: string; sort_order: number }>) {
  const resp = await api.put(`/regions/${id}`, data)
  return resp.data as RegionItem
}

export async function deleteRegion(id: string) {
  await api.delete(`/regions/${id}`)
}

export async function createSubRegion(regionId: string, data: { name: string; description?: string }) {
  const resp = await api.post(`/regions/${regionId}/sub-regions`, data)
  return resp.data as SubRegionItem
}

export async function updateSubRegion(id: string, data: Partial<{ name: string; description: string }>) {
  const resp = await api.put(`/sub-regions/${id}`, data)
  return resp.data as SubRegionItem
}

export async function deleteSubRegion(id: string) {
  await api.delete(`/sub-regions/${id}`)
}

// ========== 拓扑管理 API ==========
export interface TopologyNode {
  id: string
  name: string
  sys_name?: string | null
  device_type?: 'single' | 'stack' | 'mlag' | 'cluster' | 'unknown'
  ip: string | null
  vendor: string | null
  role: string | null
  model: string | null
  status: string  // online / offline / error / unknown
  region_id?: string | null
  sub_region_id?: string | null
  region_name?: string | null
  sub_region_name?: string | null
  virtual?: boolean  // 对端未在系统中录入
  aliases?: { id: string; name: string; ip: string }[]
}

export interface TopologyLink {
  id: string
  source: string  // 本端设备 id
  target: string  // 对端设备 id（或虚拟节点 id）
  local_port: string | null
  remote_port: string | null
  remote_sysname: string | null
  protocol: string  // lldp / cdp
  link_type: string
  is_critical: boolean
}

export interface TopologyData {
  nodes: TopologyNode[]
  links: TopologyLink[]
  stats: { node_count: number; link_count: number; virtual_count: number; critical_count: number }
}

export async function fetchTopology(regionId?: string): Promise<TopologyData> {
  const params: any = {}
  if (regionId) params.region_id = regionId
  const resp = await api.get('/topology', { params })
  return resp.data as TopologyData
}

export async function updateLinkCritical(linkId: string, isCritical: boolean): Promise<{ id: string; is_critical: boolean }> {
  const resp = await api.put(`/topology/links/${linkId}/critical`, { is_critical: isCritical })
  return resp.data as { id: string; is_critical: boolean }
}

// ========== SNMP Trap API ==========
export interface TrapLogItem {
  id: string
  source_ip: string
  source_port: number
  version: string
  community: string | null
  pdu_type: string
  variables: any[] | null
  received_at: string
  mapped_alert_id: string | null
}

export interface TrapRuleItem {
  id: string
  name: string
  oid_prefix: string
  severity: number
  message_template: string
  enabled: boolean
  created_at: string | null
}

export async function fetchTrapLogs(params?: { source_ip?: string; page?: number; page_size?: number }) {
  const resp = await api.get('/traps/logs', { params })
  return resp.data as TrapLogItem[]
}

export async function fetchTrapRules() {
  const resp = await api.get('/traps/rules')
  return resp.data as TrapRuleItem[]
}

export async function createTrapRule(data: { name: string; oid_prefix: string; severity?: number; message_template?: string; enabled?: boolean }) {
  const resp = await api.post('/traps/rules', data)
  return resp.data as TrapRuleItem
}

export async function deleteTrapRule(ruleId: string) {
  const resp = await api.delete(`/traps/rules/${ruleId}`)
  return resp.data
}

export async function fetchTrapStatus() {
  const resp = await api.get('/traps/status')
  return resp.data as { listening: boolean; port: number; community: string }
}

export default api
