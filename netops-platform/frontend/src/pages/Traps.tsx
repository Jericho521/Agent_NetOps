import { useState, useEffect, useCallback } from 'react'
import {
  fetchTrapLogs, fetchTrapRules, createTrapRule, deleteTrapRule, fetchTrapStatus,
  TrapLogItem, TrapRuleItem,
} from '../api'

function fmtTime(iso: string) {
  if (!iso) return '-'
  const d = new Date(iso)
  return d.toLocaleString('zh-CN', { hour12: false })
}

function severityText(s: number) {
  return s === 1 ? 'P1 严重' : s === 2 ? 'P2 重要' : s === 3 ? 'P3 提示' : `级别 ${s}`
}

export default function Traps() {
  const [tab, setTab] = useState<'logs' | 'rules'>('logs')
  const [logs, setLogs] = useState<TrapLogItem[]>([])
  const [rules, setRules] = useState<TrapRuleItem[]>([])
  const [status, setStatus] = useState<{ listening: boolean; port: number; community: string } | null>(null)
  const [loading, setLoading] = useState(false)

  // 规则表单
  const [showRuleForm, setShowRuleForm] = useState(false)
  const [ruleForm, setRuleForm] = useState({
    name: '', oid_prefix: '', severity: 2, message_template: '收到 SNMP Trap', enabled: true,
  })

  const loadLogs = useCallback(async () => {
    setLoading(true)
    try { setLogs(await fetchTrapLogs({ page: 1, page_size: 50 })) } finally { setLoading(false) }
  }, [])

  const loadRules = useCallback(async () => {
    try { setRules(await fetchTrapRules()) } catch { /* ignore */ }
  }, [])

  useEffect(() => {
    loadLogs()
    loadRules()
    fetchTrapStatus().then(setStatus).catch(() => {})
  }, [loadLogs, loadRules])

  async function handleCreateRule() {
    if (!ruleForm.name.trim() || !ruleForm.oid_prefix.trim()) {
      alert('请填写规则名称与 OID 前缀')
      return
    }
    try {
      await createTrapRule(ruleForm)
      setShowRuleForm(false)
      setRuleForm({ name: '', oid_prefix: '', severity: 2, message_template: '收到 SNMP Trap', enabled: true })
      loadRules()
    } catch (e: any) {
      alert('创建失败: ' + (e?.response?.data?.detail || e?.message || ''))
    }
  }

  async function handleDeleteRule(id: string) {
    if (!confirm('确认删除该 Trap 规则？')) return
    try {
      await deleteTrapRule(id)
      loadRules()
    } catch (e: any) {
      alert('删除失败: ' + (e?.response?.data?.detail || ''))
    }
  }

  return (
    <div>
      <div className="page-header">
        <h1>SNMP Trap 管理</h1>
        {status && (
          <span className={`status-badge ${status.listening ? 'status-online' : 'status-offline'}`}>
            {status.listening ? `● 监听中 (UDP :${status.port})` : '○ 未监听'}
          </span>
        )}
      </div>

      {/* Tab 切换 */}
      <div style={{ display: 'flex', gap: 8, marginBottom: 20, borderBottom: '1px solid var(--border-color)', paddingBottom: 12 }}>
        <button className="btn btn-sm" style={{ background: tab === 'logs' ? 'var(--accent-blue)' : 'var(--bg-secondary)', color: tab === 'logs' ? '#fff' : 'var(--text-primary)' }} onClick={() => setTab('logs')}>Trap 日志</button>
        <button className="btn btn-sm" style={{ background: tab === 'rules' ? 'var(--accent-blue)' : 'var(--bg-secondary)', color: tab === 'rules' ? '#fff' : 'var(--text-primary)' }} onClick={() => setTab('rules')}>映射规则 ({rules.length})</button>
      </div>

      {tab === 'logs' ? (
        <div className="card">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
            <strong>最近 Trap 接收记录</strong>
            <button className="btn btn-sm" onClick={loadLogs} disabled={loading}>{loading ? '刷新中...' : '刷新'}</button>
          </div>
          {logs.length === 0 ? (
            <p style={{ color: 'var(--text-secondary)', padding: '20px 0' }}>暂无 Trap 记录。请确认设备已配置向本平台发送 Trap（UDP :{status?.port || 1620}）。</p>
          ) : (
            <div className="table-wrapper">
              <table>
                <thead>
                  <tr><th>接收时间</th><th>源 IP</th><th>版本</th><th>PDU 类型</th><th>变量绑定</th></tr>
                </thead>
                <tbody>
                  {logs.map((l) => (
                    <tr key={l.id}>
                      <td>{fmtTime(l.received_at)}</td>
                      <td>{l.source_ip}:{l.source_port}</td>
                      <td>{l.version}</td>
                      <td>{l.pdu_type}</td>
                      <td style={{ maxWidth: 360 }}>
                        {l.variables && l.variables.length > 0 ? (
                          <details>
                            <summary style={{ cursor: 'pointer', color: 'var(--accent-blue)' }}>{l.variables.length} 项</summary>
                            <ul style={{ margin: '6px 0 0 16px', fontSize: 12 }}>
                              {l.variables.map((v: any, i: number) => (
                                <li key={i}>{v.oid || ''} = {String(v.value ?? '')}</li>
                              ))}
                            </ul>
                          </details>
                        ) : '-'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      ) : (
        <div className="card">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
            <strong>Trap → 告警 映射规则</strong>
            <button className="btn btn-sm btn-primary" onClick={() => setShowRuleForm(p => !p)}>{showRuleForm ? '取消' : '+ 新建规则'}</button>
          </div>

          {showRuleForm && (
            <div style={{ border: '1px solid var(--border-color)', borderRadius: 8, padding: 16, marginBottom: 16, background: 'var(--bg-input)' }}>
              <div className="grid-2">
                <div className="form-group">
                  <label className="label">规则名称</label>
                  <input className="input" value={ruleForm.name} onChange={e => setRuleForm(p => ({ ...p, name: e.target.value }))} placeholder="例如：接口 Down 告警" />
                </div>
                <div className="form-group">
                  <label className="label">OID 前缀（匹配 Trap OID）</label>
                  <input className="input" value={ruleForm.oid_prefix} onChange={e => setRuleForm(p => ({ ...p, oid_prefix: e.target.value }))} placeholder="例如：1.3.6.1.6.3.1.1.5" />
                </div>
                <div className="form-group">
                  <label className="label">严重级别</label>
                  <select className="input" value={ruleForm.severity} onChange={e => setRuleForm(p => ({ ...p, severity: Number(e.target.value) }))}>
                    <option value={1}>P1 严重</option>
                    <option value={2}>P2 重要</option>
                    <option value={3}>P3 提示</option>
                  </select>
                </div>
                <div className="form-group">
                  <label className="label">告警消息模板</label>
                  <input className="input" value={ruleForm.message_template} onChange={e => setRuleForm(p => ({ ...p, message_template: e.target.value }))} placeholder="收到 SNMP Trap" />
                </div>
              </div>
              <button className="btn btn-primary btn-sm" onClick={handleCreateRule}>保存规则</button>
            </div>
          )}

          {rules.length === 0 ? (
            <p style={{ color: 'var(--text-secondary)', padding: '20px 0' }}>暂无映射规则。新建规则后，匹配的 Trap 将自动生成告警。</p>
          ) : (
            <div className="table-wrapper">
              <table>
                <thead>
                  <tr><th>名称</th><th>OID 前缀</th><th>级别</th><th>状态</th><th>操作</th></tr>
                </thead>
                <tbody>
                  {rules.map((r) => (
                    <tr key={r.id}>
                      <td>{r.name}</td>
                      <td style={{ fontFamily: 'monospace', fontSize: 12 }}>{r.oid_prefix}</td>
                      <td>{severityText(r.severity)}</td>
                      <td><span className={`status-badge ${r.enabled ? 'status-online' : 'status-offline'}`}>{r.enabled ? '启用' : '停用'}</span></td>
                      <td><button className="btn btn-sm btn-danger" onClick={() => handleDeleteRule(r.id)}>删除</button></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
