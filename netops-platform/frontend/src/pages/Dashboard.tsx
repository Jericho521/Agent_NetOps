import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import ReactECharts from 'echarts-for-react'
import { fetchOverview, fetchDevices, fetchAlerts, Device, AlertItem } from '../api'

/** 格式化时间为东八区 */
function fmtTimeCN(dateStr: string | null): string {
  if (!dateStr) return '-'
  let d = new Date(dateStr)
  if (!dateStr.includes('+') && !dateStr.endsWith('Z')) {
    d = new Date(d.getTime() - d.getTimezoneOffset() * 60_000)
  }
  return d.toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
}

const STATUS_LABEL: Record<string, string> = { online: '在线', offline: '离线', error: '异常', unknown: '未知' }
const SEV_LABEL: Record<number, string> = { 0: 'P0 严重', 1: 'P1 重要', 2: 'P2 次要', 3: 'P3 提示' }

export default function Dashboard() {
  const [overview, setOverview] = useState<{ total: number; online: number; offline: number; warning: number; total_alerts_active: number } | null>(null)
  const [devices, setDevices] = useState<Device[]>([])
  const [alerts, setAlerts] = useState<AlertItem[]>([])
  const [loading, setLoading] = useState(true)

  const user = JSON.parse(localStorage.getItem('netops_user') || '{}')

  useEffect(() => {
    async function load() {
      try {
        const [ov, dev, al] = await Promise.all([
          fetchOverview(),
          fetchDevices({ page: 1, page_size: 100 }),
          fetchAlerts({ status: 'active', page_size: 8 }),
        ])
        setOverview(ov)
        setDevices(dev.items)
        setAlerts(al.items)
      } catch {
        setOverview({ total: 0, online: 0, offline: 0, warning: 0, total_alerts_active: 0 })
      } finally {
        setLoading(false)
      }
    }
    load()
  }, [])

  // 健康度环图
  const healthOption = {
    tooltip: { trigger: 'item' },
    series: [{
      type: 'pie',
      radius: ['60%', '82%'],
      avoidLabelOverlap: false,
      label: { show: false },
      data: [
        { name: '在线', value: overview?.online ?? 0, itemStyle: { color: '#3fb950' } },
        { name: '离线', value: overview?.offline ?? 0, itemStyle: { color: '#f85149' } },
        { name: '告警', value: overview?.warning ?? 0, itemStyle: { color: '#d29922' } },
      ],
    }],
  }

  // 设备厂商分布
  const VENDOR_LABEL: Record<string, string> = { huawei: '华为', h3c: 'H3C', cisco: 'Cisco', generic: '通用' }
  const vendorMap: Record<string, number> = {}
  devices.forEach(d => { const v = d.vendor || '未分类'; vendorMap[v] = (vendorMap[v] || 0) + 1 })
  const chartStyle = getComputedStyle(document.body)
  const textSecondary = chartStyle.getPropertyValue('--text-secondary').trim() || '#8b949e'
  const borderColor = chartStyle.getPropertyValue('--border-color').trim() || '#30363d'
  const vendorLabels = Object.keys(vendorMap).map(k => VENDOR_LABEL[k] || k)
  const vendorOption = {
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
    grid: { left: 60, right: 20, top: 20, bottom: 20 },
    xAxis: { type: 'category', data: vendorLabels, axisLabel: { color: textSecondary }, axisLine: { lineStyle: { color: borderColor } } },
    yAxis: { type: 'value', axisLabel: { color: textSecondary }, splitLine: { lineStyle: { color: borderColor } } },
    series: [{ type: 'bar', data: Object.values(vendorMap), itemStyle: { color: '#58a6ff', borderRadius: [4, 4, 0, 0] } }],
  }

  if (loading) return <div style={{ padding: 40, color: 'var(--text-secondary)' }}>加载中...</div>

  return (
    <div>
      <div className="page-header">
        <div>
          <h1>仪表盘</h1>
          <p style={{ color: 'var(--text-secondary)', fontSize: 14, marginTop: 4 }}>
            欢迎回来，{user?.username} · 平台整体运行态势概览
          </p>
        </div>
        <Link to="/devices" className="btn btn-primary">设备管理</Link>
      </div>

      {/* 概览卡片 */}
      <div className="grid-3" style={{ marginBottom: 20 }}>
        <StatCard label="设备总数" value={overview?.total ?? 0} color="#58a6ff" sub={`在线 ${overview?.online ?? 0} · 离线 ${overview?.offline ?? 0}`} />
        <StatCard label="活跃告警" value={overview?.total_alerts_active ?? 0} color="#f85149" sub="需关注事件" />
        <StatCard label="告警设备" value={overview?.warning ?? 0} color="#d29922" sub="处于告警中的设备" />
      </div>

      <div className="grid-2" style={{ marginBottom: 20 }}>
        <div className="card">
          <h3 style={{ marginBottom: 16 }}>设备健康度</h3>
          <ReactECharts option={healthOption} style={{ height: 240 }} />
        </div>
        <div className="card">
          <h3 style={{ marginBottom: 16 }}>设备厂商分布</h3>
          <ReactECharts option={vendorOption} style={{ height: 240 }} />
        </div>
      </div>

      {/* 最近告警 */}
      <div className="card">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
          <h3>最近活跃告警</h3>
          <Link to="/alerts" className="btn btn-sm">查看全部</Link>
        </div>
        {alerts.length === 0 ? (
          <p style={{ color: 'var(--text-secondary)' }}>暂无活跃告警，系统运行正常 ✅</p>
        ) : (
          <div className="table-wrapper">
            <table>
              <thead>
                <tr><th>级别</th><th>设备</th><th>描述</th><th>触发时间</th></tr>
              </thead>
              <tbody>
                {alerts.map(a => {
                  const dev = devices.find(d => d.id === a.device_id)
                  const catLabel: Record<string, string> = { threshold: '阈值', offline: '离线', error: '异常', link: '链路' }
                  return (
                    <tr key={a.id}>
                      <td>
                        {a.severity != null ? (
                          <span className={`severity-p${a.severity}`} style={{ padding: '2px 8px', borderRadius: 12, fontSize: 12, fontWeight: 600 }}>
                            {SEV_LABEL[a.severity] || `P${a.severity}`}
                          </span>
                        ) : (
                          <span className="tag-offline" style={{ padding: '2px 8px', borderRadius: 12, fontSize: 12, fontWeight: 600 }}>
                            {catLabel[a.category] || '状态异常'}
                          </span>
                        )}
                      </td>
                      <td>{dev?.name || a.device_id.slice(0, 8)}</td>
                      <td>{a.message}</td>
                      <td style={{ color: 'var(--text-secondary)' }}>{fmtTimeCN(a.fired_at)}</td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}

function StatCard({ label, value, color, sub }: { label: string; value: number; color: string; sub: string }) {
  return (
    <div className="card" style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
      <span style={{ color: 'var(--text-secondary)', fontSize: 14 }}>{label}</span>
      <span style={{ fontSize: 38, fontWeight: 700, color }}>{value}</span>
      <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>{sub}</span>
    </div>
  )
}
