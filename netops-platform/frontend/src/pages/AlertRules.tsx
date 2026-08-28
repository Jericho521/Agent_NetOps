import { useState, useEffect, useCallback } from 'react'
import { Link } from 'react-router-dom'
import { fetchAlertRules, createAlertRule, updateAlertRule, deleteAlertRule, AlertRule, fetchDevices, Device } from '../api'

const METRIC_OPTIONS = [
  { value: 'snmp_cpu_usage_percent', label: 'CPU 利用率 (%)' },
  { value: 'snmp_memory_usage_percent', label: '内存利用率 (%)' },
  { value: 'snmp_if_hc_in_octets', label: '接口入流量 (bps)' },
  { value: 'snmp_if_hc_out_octets', label: '接口出流量 (bps)' },
  { value: 'snmp_if_oper_status', label: '接口 oper 状态' },
]
const OPERATORS = ['>', '>=', '<', '<=', '==', '!=']
const SEV_LABEL: Record<number, string> = { 0: 'P0 严重', 1: 'P1 重要', 2: 'P2 次要', 3: 'P3 提示' }

export default function AlertRules() {
  const [rules, setRules] = useState<AlertRule[]>([])
  const [devices, setDevices] = useState<Device[]>([])
  const [loading, setLoading] = useState(true)
  const [showModal, setShowModal] = useState(false)
  const [editing, setEditing] = useState<AlertRule | null>(null)
  const [form, setForm] = useState<any>({
    name: '', metric_name: 'snmp_cpu_usage_percent', operator: '>', threshold: 85,
    critical_threshold: 95, duration_seconds: 60, severity: 1, enabled: true, device_id: '',
  })
  const [saving, setSaving] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const [r, d] = await Promise.all([fetchAlertRules(), fetchDevices({ page: 1, page_size: 100 })])
      setRules(r)
      setDevices(d.items)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  function openCreate() {
    setEditing(null)
    setForm({ name: '', metric_name: 'snmp_cpu_usage_percent', operator: '>', threshold: 85, critical_threshold: 95, duration_seconds: 60, severity: 2, enabled: true, device_id: '' })
    setShowModal(true)
  }
  function openEdit(r: AlertRule) {
    setEditing(r)
    setForm({ name: r.name, metric_name: r.metric_name, operator: r.operator, threshold: r.threshold, critical_threshold: r.critical_threshold ?? null, duration_seconds: r.duration_seconds, severity: r.severity, enabled: r.enabled, device_id: r.device_id || '' })
    setShowModal(true)
  }

  async function handleSubmit() {
    setSaving(true)
    try {
      const payload = { ...form, device_id: form.device_id || null }
      if (editing) await updateAlertRule(editing.id, payload)
      else await createAlertRule(payload)
      setShowModal(false)
      load()
    } finally {
      setSaving(false)
    }
  }

  async function handleDelete(r: AlertRule) {
    if (!confirm(`确认删除规则「${r.name}」？`)) return
    await deleteAlertRule(r.id)
    load()
  }

  function toggleEnable(r: AlertRule) {
    updateAlertRule(r.id, { enabled: !r.enabled }).then(load)
  }

  function devName(id?: string) { return id ? (devices.find(d => d.id === id)?.name || '未知') : '全部设备' }
  const metricLabel = (m: string) => METRIC_OPTIONS.find(o => o.value === m)?.label || m

  return (
    <div>
      <div className="page-header">
        <h1>告警规则</h1>
        <button className="btn btn-primary" onClick={openCreate}>新建规则</button>
      </div>

      <div className="card">
        {loading ? <p style={{ color: 'var(--text-secondary)' }}>加载中...</p> : rules.length === 0 ? (
          <p style={{ color: 'var(--text-secondary)' }}>暂无规则，点击右上角新建。</p>
        ) : (
          <div className="table-wrapper">
            <table>
              <thead>
                <tr><th>名称</th><th>指标</th><th>条件</th><th>持续</th><th>级别</th><th>作用设备</th><th>状态</th><th>操作</th></tr>
              </thead>
              <tbody>
                {rules.map(r => (
                  <tr key={r.id}>
                    <td>{r.name}</td>
                    <td>{metricLabel(r.metric_name)}</td>
                    <td>
                      {r.operator} {r.threshold}
                      {r.critical_threshold != null && (
                        <div style={{ fontSize: 11, color: 'var(--accent-red, #f85149)' }}>严重 &gt; {r.critical_threshold}</div>
                      )}
                    </td>
                    <td>{r.duration_seconds}s</td>
                    <td><span className={`severity-p${r.severity}`} style={{ padding: '2px 8px', borderRadius: 12, fontSize: 12, fontWeight: 600 }}>{SEV_LABEL[r.severity]}</span></td>
                    <td>{devName(r.device_id || undefined)}</td>
                    <td>
                      <button className="btn btn-sm" onClick={() => toggleEnable(r)} style={{ color: r.enabled ? 'var(--accent-green)' : 'var(--text-secondary)' }}>
                        {r.enabled ? '已启用' : '已停用'}
                      </button>
                    </td>
                    <td style={{ display: 'flex', gap: 6 }}>
                      <button className="btn btn-sm" onClick={() => openEdit(r)}>编辑</button>
                      <button className="btn btn-sm btn-danger" onClick={() => handleDelete(r)}>删除</button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {showModal && (
        <div className="modal-overlay" onClick={() => setShowModal(false)}>
          <div className="modal" onClick={e => e.stopPropagation()}>
            <div className="modal-header">
              <h3>{editing ? '编辑规则' : '新建规则'}</h3>
              <button className="btn btn-sm" onClick={() => setShowModal(false)}>✕</button>
            </div>

            <div className="form-group">
              <label className="label">规则名称</label>
              <input className="input" value={form.name} onChange={e => setForm({ ...form, name: e.target.value })} placeholder="如：核心交换机CPU过高" />
            </div>

            <div className="form-group">
              <label className="label">监控指标</label>
              <select className="input" value={form.metric_name} onChange={e => setForm({ ...form, metric_name: e.target.value })}>
                {METRIC_OPTIONS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
              </select>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 10 }}>
              <div className="form-group">
                <label className="label">运算符</label>
                <select className="input" value={form.operator} onChange={e => setForm({ ...form, operator: e.target.value })}>
                  {OPERATORS.map(o => <option key={o} value={o}>{o}</option>)}
                </select>
              </div>
              <div className="form-group">
                <label className="label">阈值</label>
                <input className="input" type="number" value={form.threshold} onChange={e => setForm({ ...form, threshold: Number(e.target.value) })} />
              </div>
              <div className="form-group">
                <label className="label">严重阈值（超过则升级为 P0 严重/红）</label>
                <input className="input" type="number" placeholder="可选，如 95" value={form.critical_threshold ?? ''} onChange={e => setForm({ ...form, critical_threshold: e.target.value === '' ? null : Number(e.target.value) })} />
              </div>
              <div className="form-group">
                <label className="label">持续(s)</label>
                <input className="input" type="number" value={form.duration_seconds} onChange={e => setForm({ ...form, duration_seconds: Number(e.target.value) })} />
              </div>
            </div>

            <div className="form-group">
              <label className="label">告警级别（超过「阈值」时触发）</label>
              <select className="input" value={form.severity} onChange={e => setForm({ ...form, severity: Number(e.target.value) })}>
                <option value={0}>P0 严重（红）</option>
                <option value={1}>P1 重要（橙）</option>
                <option value={2}>P2 次要（黄）</option>
                <option value={3}>P3 提示（蓝）</option>
              </select>
            </div>

            <p style={{ fontSize: 12, color: 'var(--muted)' }}>
              级别：P0 红（严重，如堆叠分裂/M-LAG 脑裂/重要链路中断，或 CPU/内存&gt;95%）、P1 橙（重要，如 CPU/内存&gt;85%）、P2 黄（次要）、P3 蓝（提示）。设备离线/采集异常不进入 P 级别体系（仅灰色状态标记）。
            </p>

            <div className="form-group">
              <label className="label">作用设备（留空=全部）</label>
              <select className="input" value={form.device_id} onChange={e => setForm({ ...form, device_id: e.target.value })}>
                <option value="">全部设备</option>
                {devices.map(d => <option key={d.id} value={d.id}>{d.name} ({d.ip})</option>)}
              </select>
            </div>

            <div className="form-group" style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <input type="checkbox" checked={form.enabled} onChange={e => setForm({ ...form, enabled: e.target.checked })} />
              <label style={{ fontSize: 14 }}>启用此规则</label>
            </div>

            <div style={{ display: 'flex', gap: 10, justifyContent: 'flex-end', marginTop: 12 }}>
              <button className="btn" onClick={() => setShowModal(false)}>取消</button>
              <button className="btn btn-primary" disabled={saving} onClick={handleSubmit}>{saving ? '保存中...' : '保存'}</button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
