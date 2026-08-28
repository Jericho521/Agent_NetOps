import { useState, useEffect, useCallback } from 'react'
import { Link } from 'react-router-dom'
import { fetchAlerts, resolveAlert, acknowledgeAlert, AlertItem, fetchDevices, Device } from '../api'

const STATUS_LABEL: Record<string, string> = { active: '活跃', acknowledged: '已确认', resolved: '已解决' }
const SEV_LABEL: Record<number, string> = { 0: 'P0 严重', 1: 'P1 重要', 2: 'P2 次要', 3: 'P3 提示' }

function fmtTimeCN(dateStr: string | null): string {
  if (!dateStr) return '-'
  let d = new Date(dateStr)
  if (!dateStr.includes('+') && !dateStr.endsWith('Z')) {
    d = new Date(d.getTime() - d.getTimezoneOffset() * 60_000)
  }
  return d.toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit' })
}

export default function Alerts() {
  const [items, setItems] = useState<AlertItem[]>([])
  const [devices, setDevices] = useState<Device[]>([])
  const [total, setTotal] = useState(0)
  const [statusFilter, setStatusFilter] = useState('active')
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(true)
  const user = JSON.parse(localStorage.getItem('netops_user') || '{}')
  const pageSize = 20

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const params: any = { status: statusFilter, page, page_size: pageSize }
      const [al, dev] = await Promise.all([
        fetchAlerts(params),
        fetchDevices({ page: 1, page_size: 100 }),
      ])
      setItems(al.items)
      setTotal(al.total)
      setDevices(dev.items)
    } finally {
      setLoading(false)
    }
  }, [statusFilter, page])

  useEffect(() => { load() }, [load])

  function devName(id?: string) {
    if (!id) return '-'
    return devices.find(d => d.id === id)?.name || id.slice(0, 8)
  }

  async function handleAck(a: AlertItem) {
    await acknowledgeAlert(a.id, user.username)
    load()
  }
  async function handleResolve(a: AlertItem) {
    await resolveAlert(a.id, user.username)
    load()
  }

  const totalPages = Math.max(1, Math.ceil(total / pageSize))

  return (
    <div>
      <div className="page-header">
        <h1>告警中心</h1>
        <Link to="/alerts/rules" className="btn btn-sm">告警规则管理</Link>
      </div>

      {/* 筛选条 */}
      <div style={{ display: 'flex', gap: 8, marginBottom: 16, alignItems: 'center' }}>
        {(['active', 'acknowledged', 'resolved', 'all'] as const).map(s => (
          <button
            key={s}
            className={`btn btn-sm ${statusFilter === s ? 'btn-primary' : ''}`}
            onClick={() => { setStatusFilter(s); setPage(1) }}
          >
            {s === 'all' ? '全部' : STATUS_LABEL[s]}
          </button>
        ))}
        <span style={{ marginLeft: 'auto', color: 'var(--text-secondary)', fontSize: 13 }}>
          共 {total} 条
        </span>
      </div>

      <div className="card">
        {loading ? <p style={{ color: 'var(--text-secondary)' }}>加载中...</p> : items.length === 0 ? (
          <p style={{ color: 'var(--text-secondary)' }}>当前筛选条件下没有告警。</p>
        ) : (
          <div className="table-wrapper">
            <table>
              <thead>
                <tr><th>级别</th><th>状态</th><th>设备</th><th>描述</th><th>触发值</th><th>触发时间</th><th>操作</th></tr>
              </thead>
              <tbody>
                {items.map(a => (
                  <tr key={a.id}>
                    <td>
                      {a.severity != null ? (
                        <span className={`severity-p${a.severity}`} style={{ padding: '2px 8px', borderRadius: 12, fontSize: 12, fontWeight: 600 }}>
                          {SEV_LABEL[a.severity] || `P${a.severity}`}
                        </span>
                      ) : (
                        <span className="tag-offline" style={{ padding: '2px 8px', borderRadius: 12, fontSize: 12, fontWeight: 600 }}>
                          {a.category === 'offline' ? '离线' : a.category === 'error' ? '采集异常' : a.category === 'link' ? '链路' : '状态异常'}
                        </span>
                      )}
                    </td>
                    <td><span className={`status-badge status-${a.status === 'active' ? 'offline' : a.status === 'acknowledged' ? 'unknown' : 'online'}`}>{STATUS_LABEL[a.status] || a.status}</span></td>
                    <td>{devName(a.device_id)}</td>
                    <td style={{ maxWidth: 320, whiteSpace: 'normal' }}>{a.message}</td>
                    <td>{a.value != null ? a.value : '-'}</td>
                    <td style={{ color: 'var(--text-secondary)' }}>{fmtTimeCN(a.fired_at)}</td>
                    <td style={{ display: 'flex', gap: 6 }}>
                      {a.status === 'active' && (
                        <button className="btn btn-sm" onClick={() => handleAck(a)}>确认</button>
                      )}
                      {a.status !== 'resolved' && (
                        <button className="btn btn-sm btn-primary" onClick={() => handleResolve(a)}>解决</button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* 分页 */}
      {totalPages > 1 && (
        <div style={{ display: 'flex', justifyContent: 'center', gap: 8, marginTop: 16 }}>
          <button className="btn btn-sm" disabled={page <= 1} onClick={() => setPage(p => p - 1)}>上一页</button>
          <span style={{ alignSelf: 'center', fontSize: 13, color: 'var(--text-secondary)' }}>{page} / {totalPages}</span>
          <button className="btn btn-sm" disabled={page >= totalPages} onClick={() => setPage(p => p + 1)}>下一页</button>
        </div>
      )}
    </div>
  )
}
