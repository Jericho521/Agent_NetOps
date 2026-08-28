import { useState, useEffect, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  fetchDevices, createDevice, updateDevice, deleteDevice, importDevicesCSV,
  testConnectivityStream, listRegions,
  Device, type RegionItem, type SubRegionItem
} from '../api'

export default function DeviceList() {
  const navigate = useNavigate()
  const [devices, setDevices] = useState<Device[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(true)
  const [showForm, setShowForm] = useState(false)
  const [editingId, setEditingId] = useState<string | null>(null)  // null=新增，非空=编辑
  const [search, setSearch] = useState('')
  const [vendorFilter, setVendorFilter] = useState('')
  const [regionFilter, setRegionFilter] = useState('')
  const [subRegionFilter, setSubRegionFilter] = useState('')

  // 区域数据（筛选 + 表单共用）
  const [regions, setRegions] = useState<RegionItem[]>([])
  useEffect(() => { listRegions().then(setRegions).catch(() => {}) }, [])

  // 表单状态
  const [form, setForm] = useState({
    name: '', sys_name: '', device_type: 'single' as const, ip: '', snmp_version: 3, snmp_port: 161,
    snmp_user: '', vendor: '', model: '', role: '',
    region_id: '', sub_region_id: '',
    snmp_community: '', snmp_auth_pass: '', snmp_priv_pass: '',
    snmp_auth_protocol: 'SHA', snmp_priv_protocol: 'AES',
    ssh_username: '', ssh_password: '', ssh_port: 22,
  })

  // 选区域时重置子区域
  function handleFormRegionChange(rid: string) {
    setForm(p => ({ ...p, region_id: rid, sub_region_id: '' }))
  }

  const loadDevices = useCallback(async () => {
    setLoading(true)
    try {
      const data = await fetchDevices({
        page, page_size: 20,
        vendor: vendorFilter || undefined,
        search: search || undefined,
        region_id: regionFilter || undefined,
        sub_region_id: subRegionFilter || undefined,
      })
      setDevices(data.items)
      setTotal(data.total)
    } catch (e) { console.error(e) }
    finally { setLoading(false) }
  }, [page, vendorFilter, search, regionFilter, subRegionFilter])

  useEffect(() => { loadDevices() }, [loadDevices])

  function closeForm() {
    setShowForm(false)
    setEditingId(null)
    setForm({
      name: '', sys_name: '', device_type: 'single' as const, ip: '', snmp_version: 3, snmp_port: 161,
      snmp_user: '', vendor: '', model: '', role: '',
      region_id: '', sub_region_id: '',
      snmp_community: '', snmp_auth_pass: '', snmp_priv_pass: '',
      snmp_auth_protocol: 'SHA', snmp_priv_protocol: 'AES',
      ssh_username: '', ssh_password: '', ssh_port: 22,
    })
  }

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault()
    try {
      await createDevice(form)
      closeForm()
      loadDevices()
    } catch (err: any) {
      alert(err.response?.data?.detail || '创建失败')
    }
  }

  function handleEdit(d: Device) {
    setEditingId(d.id)
    setShowForm(true)
    setForm({
      name: d.name, sys_name: d.sys_name || '', device_type: (d.device_type as any) || 'single',
      ip: d.ip, snmp_version: d.snmp_version, snmp_port: d.snmp_port,
      snmp_user: d.snmp_user || '', vendor: d.vendor || '', model: d.model || '', role: d.role || '',
      region_id: d.region_id || '', sub_region_id: d.sub_region_id || '',
      snmp_community: '', snmp_auth_pass: '', snmp_priv_pass: '',
      snmp_auth_protocol: 'SHA', snmp_priv_protocol: 'AES',
      ssh_username: '', ssh_password: '', ssh_port: d.ssh_port || 22,
    })
  }

  async function handleUpdate(e: React.FormEvent) {
    e.preventDefault()
    if (!editingId) return
    try {
      await updateDevice(editingId, form)
      closeForm()
      loadDevices()
    } catch (err: any) {
      alert(err.response?.data?.detail || '更新失败')
    }
  }

  async function handleDelete(id: string, name: string) {
    if (!confirm(`确定删除设备 "${name}" 吗？`)) return
    await deleteDevice(id)
    loadDevices()
  }

  // 测试连通性弹窗状态
  const [testModal, setTestModal] = useState<{
    open: boolean
    deviceName: string
    stages: Record<string, any>
    overall: number
    done: boolean
    success: boolean
    errorMsg: string
  }>({ open: false, deviceName: '', stages: {}, overall: 0, done: false, success: false, errorMsg: '' })

  async function handleTest(id: string, name: string) {
    setTestModal({ open: true, deviceName: name, stages: {}, overall: 0, done: false, success: false, errorMsg: '' })
    try {
      await testConnectivityStream(id, (stage) => {
        setTestModal(prev => {
          const stages = { ...prev.stages, [stage.stage]: stage }
          const prog = stage.progress ?? prev.overall
          return { ...prev, stages, overall: prog }
        })
      })
      // 根据各阶段实际状态判断最终结果
      setTestModal(prev => {
        const hasFailed = Object.values(prev.stages).some((s: any) => s?.status === 'failed')
        const connectStage = prev.stages['connect']
        const connectFailed = connectStage?.status === 'failed'
        return {
          ...prev,
          done: true,
          success: !connectFailed,
          errorMsg: connectFailed ? (connectStage.detail?.error || 'SNMP 连接失败') : (hasFailed ? '部分测试项失败' : ''),
        }
      })
    } catch (err: any) {
      const msg = err?.message || '测试连接失败'
      setTestModal(prev => ({ ...prev, done: true, success: false, errorMsg: msg, overall: 100 }))
    }
  }

  function closeTestModal() {
    setTestModal(prev => ({ ...prev, open: false }))
    loadDevices()
  }

  async function handleImport(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    if (!file) return
    try {
      const res = await importDevicesCSV(file)
      alert(res.message + (res.detail?.errors?.length ? `\n错误: ${res.detail.errors.join('\n')}` : ''))
      loadDevices()
    } catch (err: any) {
      alert(err.response?.data?.detail || '导入失败')
    }
    // 重置 input
    e.target.value = ''
  }

  function statusClass(s: string): string {
    switch (s) {
      case 'online': return 'status-online'
      case 'offline': return 'status-offline'
      case 'error': return 'status-error'
      default: return 'status-unknown'
    }
  }

  function statusText(s: string): string {
    const map: Record<string, string> = { online: '在线', offline: '不可达', error: '异常', unknown: '未知' }
    return map[s] || s
  }

  // 厂商英文 → 中文映射
  const vendorMap: Record<string, string> = { huawei: '华为', h3c: 'H3C', cisco: 'Cisco', generic: '通用' }
  // 角色英文 → 中文映射
  const roleMap: Record<string, string> = { switch: '交换机', router: '路由器', firewall: '防火墙', core: '核心交换机', access: '接入层', aggregation: '汇聚层' }
  function vendorText(v: string | null): string { return v ? (vendorMap[v] || v) : '-' }
  function roleText(r: string | null): string { return r ? (roleMap[r] || r) : '-' }

  return (
    <div>
      <div className="page-header">
        <h1>设备管理</h1>
        <div style={{ display: 'flex', gap: 10 }}>
          <label className="btn btn-sm" style={{ cursor: 'pointer' }}>
            📥 导入 CSV
            <input type="file" accept=".csv" onChange={handleImport} hidden />
          </label>
          <button className="btn btn-primary" onClick={() => { closeForm(); setShowForm(true) }}>
            ➕ 添加设备
          </button>
        </div>
      </div>

      {/* 搜索和筛选 */}
      <div style={{ display: 'flex', gap: 12, marginBottom: 20, flexWrap: 'wrap', alignItems: 'center' }}>
        <input
          className="input"
          placeholder="搜索名称或 IP..."
          value={search}
          onChange={e => { setSearch(e.target.value); setPage(1) }}
          style={{ maxWidth: 200 }}
        />
        <select
          className="input"
          value={vendorFilter}
          onChange={e => { setVendorFilter(e.target.value); setPage(1) }}
          style={{ maxWidth: 120 }}
        >
          <option value="">全部厂商</option>
          <option value="huawei">华为</option>
          <option value="h3c">H3C</option>
          <option value="cisco">Cisco</option>
          <option value="generic">通用</option>
        </select>

        {/* 区域筛选 */}
        <select
          className="input"
          value={regionFilter}
          onChange={e => { setRegionFilter(e.target.value); setSubRegionFilter(''); setPage(1) }}
          style={{ maxWidth: 140 }}
        >
          <option value="">全部区域</option>
          {regions.map(r => (
            <option key={r.id} value={r.id}>{r.name}</option>
          ))}
        </select>

        {/* 子区域筛选 */}
        {regionFilter && (() => {
          const r = regions.find(x => x.id === regionFilter)
          return (
            <select
              className="input"
              value={subRegionFilter}
              onChange={e => { setSubRegionFilter(e.target.value); setPage(1) }}
              style={{ maxWidth: 140 }}
            >
              <option value="">全部子区域</option>
              {(r?.sub_regions || []).map(sr => (
                <option key={sr.id} value={sr.id}>{sr.name}</option>
              ))}
            </select>
          )
        })()}

        <span style={{ color: 'var(--text-secondary)', lineHeight: '36px' }}>
          共 {total} 台设备
        </span>
      </div>

      {/* 添加设备表单 */}
      {showForm && (
        <div className="card" style={{ marginBottom: 20 }}>
          <h3 style={{ marginBottom: 16 }}>{editingId ? '编辑设备' : '添加新设备'}</h3>
          <form onSubmit={editingId ? handleUpdate : handleCreate}>
            <div className="grid-2">
              <div className="form-group">
                <label className="label">设备名称 *</label>
                <input className="input" required value={form.name}
                  onChange={e => setForm(p => ({ ...p, name: e.target.value }))} placeholder="如：边界交换机-S620" />
              </div>
              <div className="form-group">
                <label className="label">系统名 (LLDP/CDP)</label>
                <input className="input" value={form.sys_name}
                  onChange={e => setForm(p => ({ ...p, sys_name: e.target.value }))} placeholder="如 DMZ-2-HJ，用于拓扑匹配" />
              </div>
              <div className="form-group">
                <label className="label">IP 地址 *</label>
                <input className="input" required value={form.ip}
                  onChange={e => setForm(p => ({ ...p, ip: e.target.value }))} placeholder="192.168.10.1" />
              </div>
              <div className="form-group">
                <label className="label">网元类型</label>
                <select className="input" value={form.device_type}
                  onChange={e => setForm(p => ({ ...p, device_type: e.target.value as any }))}>
                  <option value="single">单机</option>
                  <option value="stack">堆叠</option>
                  <option value="mlag">M-LAG</option>
                  <option value="cluster">集群</option>
                </select>
              </div>

              <div className="form-group">
                <label className="label">SNMP 版本</label>
                <select className="input" value={form.snmp_version}
                  onChange={e => setForm(p => ({ ...p, snmp_version: Number(e.target.value) }))}>
                  <option value={2}>v2c</option>
                  <option value={3}>v3（推荐）</option>
                </select>
              </div>
              <div className="form-group">
                <label className="label">厂商</label>
                <select className="input" value={form.vendor}
                  onChange={e => setForm(p => ({ ...p, vendor: e.target.value }))}>
                  <option value="">通用</option>
                  <option value="huawei">华为</option>
                  <option value="h3c">H3C</option>
                  <option value="cisco">Cisco</option>
                </select>
              </div>

              {/* SNMP v2c 凭据 */}
              {form.snmp_version === 2 && (
                <div className="form-group">
                  <label className="label">Community（团体字）</label>
                  <input className="input" value={form.snmp_community}
                    onChange={e => setForm(p => ({ ...p, snmp_community: e.target.value }))} placeholder="public" />
                </div>
              )}

              {/* SNMP v3 凭据 */}
              {form.snmp_version === 3 && (
                <>
                  <div className="form-group">
                    <label className="label">SNMP 用户名</label>
                    <input className="input" value={form.snmp_user}
                      onChange={e => setForm(p => ({ ...p, snmp_user: e.target.value }))} placeholder="snmpuser" />
                  </div>
                  <div className="form-group">
                    <label className="label">认证密码</label>
                    <input className="input" type="password" value={form.snmp_auth_pass}
                      onChange={e => setForm(p => ({ ...p, snmp_auth_pass: e.target.value }))} />
                  </div>
                  <div className="form-group">
                    <label className="label">加密密码</label>
                    <input className="input" type="password" value={form.snmp_priv_pass}
                      onChange={e => setForm(p => ({ ...p, snmp_priv_pass: e.target.value }))} />
                  </div>
                </>
              )}

              {/* SSH 凭据（配置备份用） */}
              <div className="form-group">
                <label className="label">SSH 用户名</label>
                <input className="input" value={form.ssh_username}
                  onChange={e => setForm(p => ({ ...p, ssh_username: e.target.value }))} placeholder="admin" />
              </div>
              <div className="form-group">
                <label className="label">SSH 密码</label>
                <input className="input" type="password" value={form.ssh_password}
                  onChange={e => setForm(p => ({ ...p, ssh_password: e.target.value }))} />
              </div>
              <div className="form-group">
                <label className="label">SSH 端口</label>
                <input className="input no-spin" type="text" inputMode="numeric" value={form.ssh_port}
                  onChange={e => {
                    const v = e.target.value.replace(/\D/g, '')
                    setForm(p => ({ ...p, ssh_port: v ? Math.min(65535, parseInt(v, 10)) : 0 }))
                  }} />
              </div>

              <div className="form-group">
                <label className="label">角色</label>
                <select className="input" value={form.role}
                  onChange={e => setForm(p => ({ ...p, role: e.target.value }))}>
                  <option value="">未指定</option>
                  <option value="switch">交换机</option>
                  <option value="router">路由器</option>
                  <option value="firewall">防火墙</option>
                  <option value="core">核心</option>
                  <option value="access">接入层</option>
                </select>
              </div>
              <div className="form-group">
                <label className="label">所属区域</label>
                <select className="input" value={form.region_id}
                  onChange={e => handleFormRegionChange(e.target.value)}>
                  <option value="">未指定</option>
                  {regions.map(r => (
                    <option key={r.id} value={r.id}>{r.name}</option>
                  ))}
                </select>
              </div>
              {form.region_id && (() => {
                const r = regions.find(x => x.id === form.region_id)
                return (
                  <div className="form-group">
                    <label className="label">子区域</label>
                    <select className="input" value={form.sub_region_id}
                      onChange={e => setForm(p => ({ ...p, sub_region_id: e.target.value }))}>
                      <option value="">未指定</option>
                      {(r?.sub_regions || []).map(sr => (
                        <option key={sr.id} value={sr.id}>{sr.name}</option>
                      ))}
                    </select>
                  </div>
                )
              })()}
            </div>

            <div style={{ marginTop: 16, display: 'flex', gap: 10 }}>
              <button type="submit" className="btn btn-primary">{editingId ? '保存' : '创建'}</button>
              <button type="button" className="btn" onClick={closeForm}>取消</button>
            </div>
          </form>
        </div>
      )}

      {/* 设备表格 */}
      <div className="card table-wrapper">
        {loading ? (
          <div style={{ textAlign: 'center', padding: 40, color: 'var(--text-secondary)' }}>加载中...</div>
        ) : devices.length === 0 ? (
          <div style={{ textAlign: 'center', padding: 40, color: 'var(--text-secondary)' }}>
            暂无设备，点击「添加设备」开始使用
          </div>
        ) : (
          <table>
            <thead>
              <tr>
                <th>名称</th><th>IP</th><th>厂商</th><th>角色</th>
                <th>区域</th>
                <th>SNMP</th><th>状态</th><th>最后采集</th><th>操作</th>
              </tr>
            </thead>
            <tbody>
              {devices.map(d => (
                <tr key={d.id}>
                  <td>
                    <a href="#" onClick={(e) => { e.preventDefault(); navigate(`/devices/${d.id}`) }}
                      style={{ fontWeight: 600 }}>{d.name}</a>
                  </td>
                  <td><code>{d.ip}</code></td>
                  <td>{vendorText(d.vendor)}</td>
                  <td>{roleText(d.role)}</td>
                  <td style={{ fontSize: 13 }}>
                    {d.region_name ? (
                      <>
                        {d.region_name}
                        {d.sub_region_name && <span style={{ color: 'var(--text-secondary)' }} > / {d.sub_region_name}</span>}
                      </>
                    ) : '-'}
                  </td>
                  <td>v{d.snmp_version}:{d.snmp_port}</td>
                  <td><span className={`status-badge ${statusClass(d.status)}`}>{statusText(d.status)}</span></td>
                  <td style={{ fontSize: 13, color: 'var(--text-secondary)' }}>
                    {d.last_seen_at ? (() => {
                      const dt = new Date(d.last_seen_at!)
                      const s = d.last_seen_at!
                      if (!s.includes('+') && !s.endsWith('Z')) {
                        const off = dt.getTimezoneOffset() * 60_000
                        return new Date(dt.getTime() - off).toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit' })
                      }
                      return dt.toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit' })
                    })() : '-'}
                  </td>
                  <td>
                    <div style={{ display: 'flex', gap: 6 }}>
                      <button className="btn btn-sm" onClick={() => handleEdit(d)}>编辑</button>
                      <button className="btn btn-sm" onClick={() => handleTest(d.id, d.name)}>测试</button>
                      <button className="btn btn-sm btn-danger" onClick={() => handleDelete(d.id, d.name)}>删除</button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}

        {/* 分页 */}
        {total > 20 && (
          <div style={{ display: 'flex', justifyContent: 'center', gap: 8, paddingTop: 16 }}>
            <button className="btn btn-sm" disabled={page <= 1} onClick={() => setPage(p => p - 1)}>上一页</button>
            <span style={{ lineHeight: '32px', fontSize: 14, color: 'var(--text-secondary)' }}>
              第 {page} / {Math.ceil(total / 20)} 页
            </span>
            <button className="btn btn-sm" disabled={page >= Math.ceil(total / 20)} onClick={() => setPage(p => p + 1)}>下一页</button>
          </div>
        )}
      </div>

      {/* 测试连通性弹窗 */}
      {testModal.open && (
        <div className="modal-overlay" onClick={closeTestModal}>
          <div className="modal" onClick={e => e.stopPropagation()}>
            <div className="modal-header">
              <h3 style={{ margin: 0, fontSize: 16 }}>🔌 测试连通性 — {testModal.deviceName}</h3>
              <button className="btn btn-sm" onClick={closeTestModal} style={{ padding: '2px 8px' }}>✕</button>
            </div>

            {/* 总进度条 */}
            <div style={{ margin: '16px 0' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, color: 'var(--text-secondary)', marginBottom: 4 }}>
                <span>总体进度</span>
                <span>{testModal.overall}%</span>
              </div>
              <div style={{ height: 8, background: 'var(--bg-secondary)', borderRadius: 4, overflow: 'hidden' }}>
                <div style={{
                  height: '100%', width: `${testModal.overall}%`,
                  background: testModal.done && !testModal.success ? 'var(--danger)' : 'var(--accent)',
                  transition: 'width 0.3s ease',
                }} />
              </div>
            </div>

            {/* 分阶段详情 */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
              {['connect', 'sysinfo', 'interfaces', 'finish'].map(key => {
                const s = testModal.stages[key]
                if (!s) {
                  return (
                    <div key={key} style={{ display: 'flex', alignItems: 'center', gap: 10, opacity: 0.4 }}>
                      <span style={{ fontSize: 16 }}>○</span>
                      <span style={{ fontSize: 13, color: 'var(--text-secondary)' }}>等待中...</span>
                    </div>
                  )
                }
                const icon = s.status === 'success' ? '✅' : s.status === 'failed' ? '❌' : '⏳'
                const color = s.status === 'failed' ? 'var(--danger)' : s.status === 'success' ? 'var(--success)' : 'var(--text-primary)'
                return (
                  <div key={key} style={{ display: 'flex', alignItems: 'flex-start', gap: 10 }}>
                    <span style={{ fontSize: 16 }}>{icon}</span>
                    <div style={{ flex: 1 }}>
                      <div style={{ fontSize: 13, color }}>{s.message}</div>
                      {s.detail && Object.keys(s.detail).length > 0 && (
                        <pre style={{
                          margin: '4px 0 0', fontSize: 11, color: 'var(--text-secondary)',
                          background: 'var(--bg-secondary)', padding: '6px 8px', borderRadius: 4,
                          whiteSpace: 'pre-wrap', wordBreak: 'break-all', maxHeight: 120, overflowY: 'auto',
                        }}>
                          {JSON.stringify(s.detail, null, 2)}
                        </pre>
                      )}
                    </div>
                  </div>
                )
              })}
            </div>

            {/* 底部结果 */}
            {testModal.done && (
              <div style={{ marginTop: 16, textAlign: 'center' }}>
                {testModal.success ? (
                  <div style={{ color: 'var(--success)', fontSize: 14, fontWeight: 600 }}>✅ 设备在线，连接成功</div>
                ) : (
                  <div style={{ color: 'var(--danger)', fontSize: 14, fontWeight: 600 }}>
                    ❌ 连接失败{testModal.errorMsg ? `: ${testModal.errorMsg}` : ''}
                  </div>
                )}
                <button className="btn btn-primary" style={{ marginTop: 12 }} onClick={closeTestModal}>关闭</button>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
