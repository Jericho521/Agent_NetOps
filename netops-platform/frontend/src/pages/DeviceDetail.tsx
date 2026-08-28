import { useState, useEffect, useRef } from 'react'
import { useParams, Link } from 'react-router-dom'
import ReactECharts from 'echarts-for-react'
import { fetchDevice, fetchMetrics, updateDevice, Device, MetricsResponse } from '../api'
import ConfigBackupPanel from '../components/ConfigBackupPanel'

// ========== 常量映射表 ==========
const VENDOR_MAP: Record<string, string> = { huawei: '华为', h3c: 'H3C', cisco: 'Cisco', generic: '通用' }
const ROLE_MAP: Record<string, string> = { switch: '交换机', router: '路由器', firewall: '防火墙', core: '核心交换机', access: '接入层', aggregation: '汇聚层' }
const TYPE_MAP: Record<string, string> = { single: '单机', stack: '堆叠', mlag: 'M-LAG', cluster: '集群' }

/** metric_name → 中文标题 */
const METRIC_TITLE_MAP: Record<string, string> = {
  'snmp_cpu_usage_percent': 'CPU 利用率',
  'snmp_memory_usage_percent': '内存利用率',
  'snmp_if_hc_in_octets': '接口入流量',
  'snmp_if_hc_out_octets': '接口出流量',
  'snmp_if_in_octets': '接口入流量(32位)',
  'snmp_if_out_octets': '接口出流量(32位)',
  'snmp_if_oper_status': '接口状态',
  'snmp_if_admin_status': '接口管理状态',
  'snmp_if_speed': '接口速率',
}

/** metric_name → 基础单位（用于 tooltip 格式化） */
const METRIC_BASE_UNIT_MAP: Record<string, { baseUnit: string; isBps?: boolean }> = {
  'snmp_cpu_usage_percent': { baseUnit: '%' },
  'snmp_memory_usage_percent': { baseUnit: '%' },
  'snmp_if_hc_in_octets': { baseUnit: 'bps', isBps: true },
  'snmp_if_hc_out_octets': { baseUnit: 'bps', isBps: true },
  'snmp_if_in_octets': { baseUnit: 'bps', isBps: true },
  'snmp_if_out_octets': { baseUnit: 'bps', isBps: true },
  'snmp_if_oper_status': { baseUnit: '' },
  'snmp_if_admin_status': { baseUnit: '' },
  'snmp_if_speed': { baseUnit: 'bps', isBps: true },
}

/**
 * 根据数据最大值自动选择合适的带宽单位及缩放因子
 * 返回 { label, divisor, suffix }
 */
function autoBpsUnit(maxVal: number): { label: string; divisor: number; suffix: string } {
  if (maxVal >= 1e9) return { label: '速率 (Gbps)', divisor: 1e9, suffix: ' Gbps' }
  if (maxVal >= 1e6) return { label: '速率 (Mbps)', divisor: 1e6, suffix: ' Mbps' }
  if (maxVal >= 1e3) return { label: '速率 (Kbps)', divisor: 1e3, suffix: ' Kbps' }
  return { label: '速率 (bps)', divisor: 1, suffix: ' bps' }
}

/** 将 bps → 可读带宽字符串（后端已转 bps） */
function formatBps(bps: number): string {
  if (bps == null || isNaN(bps)) return '-'
  if (bps >= 1e9) return (bps / 1e9).toFixed(2) + ' Gbps'
  if (bps >= 1e6) return (bps / 1e6).toFixed(2) + ' Mbps'
  if (bps >= 1e3) return (bps / 1e3).toFixed(2) + ' Kbps'
  return bps.toFixed(2) + ' bps'
}

/** 格式化时间为东八区 (+8) */
function fmtTimeCN(dateStr: string | null): string {
  if (!dateStr) return '-'
  // 后端存的是 UTC 时间（可能带或不带 +00:00 时区标记）
  // 统一当 UTC 解析，再转北京时间
  let d = new Date(dateStr)
  // 如果字符串不带时区后缀（naive datetime），浏览器会按本地时区解析
  // 需要手动修正：减去本地偏移量得到真正的 UTC 时间戳
  if (!dateStr.includes('+') && !dateStr.endsWith('Z')) {
    const localOffset = d.getTimezoneOffset() * 60_000 // 本地与 UTC 的差值(ms)
    d = new Date(d.getTime() - localOffset) // 修正为 UTC
  }
  return d.toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai', year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit' })
}

export default function DeviceDetail() {
  const { id } = useParams<{ id: string }>()
  const [device, setDevice] = useState<Device | null>(null)
  const [metricsData, setMetricsData] = useState<MetricsResponse[]>([])
  const [loading, setLoading] = useState(true)
  const [rangeHours, setRangeHours] = useState(1)

  // 接口选择：{ metric_name: 选中的接口名 }
  const [selectedIface, setSelectedIface] = useState<Record<string, string>>({})

  // 型号编辑状态
  const [editingModel, setEditingModel] = useState(false)
  const [modelInput, setModelInput] = useState('')
  const modelRef = useRef<HTMLInputElement>(null)

  // SSH 凭据状态
  const [editingSsh, setEditingSsh] = useState(false)
  const [sshUsername, setSshUsername] = useState('')
  const [sshPassword, setSshPassword] = useState('')
  const [sshPort, setSshPort] = useState(22)
  const [savingSsh, setSavingSsh] = useState(false)

  useEffect(() => {
    async function load(isInitial = false) {
      if (!id) return
      // 仅在首次加载时显示全屏 loading，轮询刷新时保留旧图表避免闪烁
      if (isInitial) setLoading(true)
      try {
        const [devData, metricsResult] = await Promise.all([
          fetchDevice(id),
          fetchMetrics(id, 'snmp_cpu_usage_percent,snmp_memory_usage_percent,snmp_if_hc_in_octets,snmp_if_hc_out_octets', rangeHours, 60),
        ])
        setDevice(devData)
        setModelInput(devData.model || '')
        setSshPort(devData.ssh_port || 22)
        setMetricsData(metricsResult)

        // 初始化接口选择：优先从 localStorage 恢复用户上次的选择
        const savedKey = `netops_iface_sel_${id}`
        const savedSel: Record<string, string> = JSON.parse(localStorage.getItem(savedKey) || '{}')
        const ifaceSel: Record<string, string> = {}
        for (const m of metricsResult) {
          if (isInterfaceMetric(m.metric_name)) {
            // 优先用保存的值，其次默认选第一个接口
            if (savedSel[m.metric_name]) {
              ifaceSel[m.metric_name] = savedSel[m.metric_name]
            } else if (m.data && m.data.length > 0) {
              const first = m.data[0]
              ifaceSel[m.metric_name] = first.metric.ifName || first.metric.ifIndex || `系列${first.metric.ifIndex || '?'}`
            }
          }
        }
        setSelectedIface(ifaceSel)
      } catch (e) { console.error(e) }
      finally { setLoading(false) }
    }
    load(true)

    const timer = setInterval(() => load(false), 60000)
    return () => clearInterval(timer)
  }, [id, rangeHours])

  if (!device) {
    return <div style={{ textAlign: 'center', padding: 40 }}>加载中...</div>
  }

  function isInterfaceMetric(name: string): boolean {
    return name.includes('if_') || name.includes('interface')
  }

  function getIfaceList(metric: MetricsResponse): string[] {
    if (!metric.data) return []
    return metric.data.map((s, idx) => s.metric.ifName || s.metric.ifIndex || `系列${idx + 1}`)
  }

  /** 保存型号 */
  async function saveModel() {
    if (!id) return
    try {
      await updateDevice(id, { model: modelInput })
      setDevice(prev => prev ? { ...prev, model: modelInput } : null)
      setEditingModel(false)
    } catch (e) { console.error(e) }
  }

  /** 保存 SSH 凭据 */
  async function saveSsh() {
    if (!id) return
    setSavingSsh(true)
    try {
      await updateDevice(id, { ssh_username: sshUsername, ssh_password: sshPassword, ssh_port: sshPort })
      setDevice(prev => prev ? { ...prev, ssh_port: sshPort } : null)
      setEditingSsh(false)
    } catch (e) { console.error(e) }
    finally { setSavingSsh(false) }
  }

  /** 将 MetricsResponse 转换为 ECharts option */
  function getChartOption(metric: MetricsResponse): object {
    const allSeries = metric.data || []

    // 如果是接口指标，按选择的单接口过滤
    let displaySeries = allSeries
    const selName = selectedIface[metric.metric_name]
    if (isInterfaceMetric(metric.metric_name) && selName) {
      displaySeries = allSeries.filter((s, idx) => {
        const name = s.metric.ifName || s.metric.ifIndex || getMetricTitle(metric.metric_name)
        return name === selName
      })
    }

    if (displaySeries.length === 0) {
      return {
        title: { text: `${getMetricTitle(metric.metric_name)}（暂无数据）`, left: 'center', top: 10, textStyle: { color: '#8b949e', fontSize: 14 } },
        xAxis: { type: 'category', data: [] },
        yAxis: { type: 'value' },
        series: [],
      }
    }

    const timeLabels = displaySeries[0].values.map(v =>
      new Date(v.timestamp * 1000).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', second: '2-digit' })
    )

    const baseUnitInfo = METRIC_BASE_UNIT_MAP[metric.metric_name]

    // 读取当前主题色，让图表网格/文字随深浅色切换
    const style = getComputedStyle(document.body)
    const textSecondary = style.getPropertyValue('--text-secondary').trim() || '#8b949e'
    const borderColor = style.getPropertyValue('--border-color').trim() || '#30363d'

    // 收集所有有效值，用于 bps 类指标自动选择单位
    let maxVal = 0
    const seriesData = displaySeries.map((s) => {
      const vals = s.values.map(v => (v.value === -1 ? null : v.value ?? null))
      for (const v of vals) { if (v != null && v > maxVal) maxVal = v }
      return {
        name: s.metric.ifName || s.metric.ifIndex || getMetricTitle(metric.metric_name),
        type: 'line' as const,
        smooth: true,
        symbol: 'none',
        lineStyle: { width: 2 },
        data: vals,
      }
    })

    // bps 类指标：根据最大值自动切换单位
    const bpsAuto = baseUnitInfo?.isBps ? autoBpsUnit(maxVal) : null

    const colors = ['#58a6ff', '#3fb950', '#f85149', '#d29922', '#a371f7', '#79c0ff', '#db61a2', '#f0883e']

    return {
      tooltip: {
        trigger: 'axis',
        formatter(params: any) {
          if (!Array.isArray(params)) params = [params]
          let tip = `<div style="font-size:12px">${params[0].axisValue}</div>`
          for (const p of params) {
            const val = p.data as number
            if (val === -1 || val == null) {
              tip += `<div style="font-size:11px;margin-top:2px">${p.marker} ${p.seriesName}: <b style="color:#888">不支持</b></div>`
            } else if (baseUnitInfo?.isBps) {
              tip += `<div style="font-size:11px;margin-top:2px">${p.marker} ${p.seriesName}: <b>${formatBps(val)}</b></div>`
            } else {
              const suffix = baseUnitInfo?.baseUnit ? ` ${baseUnitInfo.baseUnit}` : ''
              tip += `<div style="font-size:11px;margin-top:2px">${p.marker} ${p.seriesName}: <b>${val}${suffix}</b></div>`
            }
          }
          return tip
        },
      },
      legend: { bottom: 0, textStyle: { color: textSecondary, fontSize: 11 } },
      grid: { top: 40, bottom: 50, left: 70, right: 20 },
      color: colors,
      xAxis: {
        type: 'category',
        data: timeLabels,
        axisLabel: { color: textSecondary, fontSize: 11 },
        axisLine: { lineStyle: { color: borderColor } },
      },
      yAxis: {
        type: 'value',
        inverse: false,
        axisLabel: {
          color: textSecondary, fontSize: 11,
          formatter: (val: number) => {
            if (val == null || isNaN(val)) return '-'
            if (bpsAuto) {
              // 按自动选择的单位缩放显示
              return (val / bpsAuto.divisor).toFixed(bpsAuto.divisor >= 1e6 ? 1 : 0)
            }
            if (baseUnitInfo?.baseUnit === '%') return `${Math.round(val)}%`
            return val.toString()
          },
        },
        splitLine: { lineStyle: { color: borderColor } },
        name: bpsAuto?.label || (baseUnitInfo?.baseUnit === '%' ? '利用率 (%)' : ''),
        nameTextStyle: { color: textSecondary, fontSize: 11 },
      },
      series: seriesData,
    }
  }

  function getMetricTitle(name: string): string {
    return METRIC_TITLE_MAP[name] || name.replace(/_/g, ' ')
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

  function vendorText(v: string | null): string { return v ? (VENDOR_MAP[v] || v) : '通用' }
  function roleText(r: string | null): string { return r ? (ROLE_MAP[r] || r) : '-' }

  return (
    <div>
      {/* 返回导航 */}
      <div style={{ marginBottom: 20 }}>
        <Link to="/devices" style={{ fontSize: 14 }}>&larr; 返回设备列表</Link>
      </div>

      {/* 设备信息卡片 */}
      <div className="card" style={{ marginBottom: 24 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
          <div>
            <h1 style={{ fontSize: 22, marginBottom: 8 }}>{device.name}</h1>
            <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap', fontSize: 14, color: 'var(--text-secondary)', alignItems: 'center' }}>
              <span><code>{device.ip}</code></span>
              <span>厂商: {vendorText(device.vendor)}</span>
              {/* 型号 - 已自动识别则只读展示，否则可点击录入 */}
              <span>
                型号:
                {device.model ? (
                  <span style={{ color: 'var(--text-primary)' }}>
                    {device.model}
                    <span style={{ marginLeft: 6, fontSize: 12, color: 'var(--text-secondary)', cursor: 'pointer', textDecoration: 'underline' }}
                          onClick={() => { setModelInput(device.model || ''); setEditingModel(true); setTimeout(() => modelRef.current?.focus(), 50) }}>
                      修改
                    </span>
                  </span>
                ) : editingModel ? (
                  <>
                    <input
                      ref={modelRef}
                      value={modelInput}
                      onChange={e => setModelInput(e.target.value)}
                      onKeyDown={e => e.key === 'Enter' && saveModel()}
                      onBlur={() => { /* 延迟让 onClick 优先 */ setTimeout(() => { if (editingModel) saveModel() }, 150) }}
                      autoFocus
                      style={{
                        background: 'var(--bg-secondary)', border: '1px solid #58a6ff',
                        borderRadius: 4, color: 'var(--text-primary)', padding: '1px 6px',
                        fontSize: 13, width: 140, marginLeft: 4,
                      }}
                    />
                    <button onMouseDown={e => e.preventDefault()} onClick={saveModel} className="btn btn-sm" style={{ marginLeft: 4, padding: '1px 8px', fontSize: 12 }}>保存</button>
                  </>
                ) : (
                  <span style={{ cursor: 'pointer', textDecoration: 'underline', color: 'var(--text-primary)' }}
                     onClick={() => { setEditingModel(true); setTimeout(() => modelRef.current?.focus(), 50) }}>
                    点击录入
                  </span>
                )}
              </span>
              <span>角色: {roleText(device.role)}</span>
              <span>
                网元类型:
                <select
                  value={device.device_type || 'single'}
                  onChange={async (e) => {
                    const v = e.target.value as 'single' | 'stack' | 'mlag' | 'cluster'
                    await updateDevice(device.id, { device_type: v })
                    setDevice(prev => prev ? { ...prev, device_type: v } : null)
                  }}
                  style={{
                    background: 'var(--bg-secondary)', border: '1px solid var(--border-color)',
                    borderRadius: 4, color: 'var(--text-primary)', padding: '1px 4px',
                    fontSize: 13, marginLeft: 4,
                  }}
                >
                  <option value="single">单机</option>
                  <option value="stack">堆叠</option>
                  <option value="mlag">M-LAG</option>
                  <option value="cluster">集群</option>
                </select>
              </span>
              {device.sys_name && <span>系统名: {device.sys_name}</span>}
              <span>SNMP v{device.snmp_version}:{device.snmp_port}</span>
              <span>区域: {device.region || '未分配'}</span>
            </div>
          </div>
          <div style={{ textAlign: 'right' }}>
            <span className={`status-badge ${statusClass(device.status)}`} style={{ fontSize: 14, padding: '4px 14px' }}>
              {statusText(device.status)}
            </span>
            <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginTop: 6 }}>
              最后采集: {fmtTimeCN(device.last_seen_at)}
            </div>
          </div>
        </div>
      </div>

      {/* SSH 凭据设置 */}
      <div className="card" style={{ marginBottom: 20, padding: '12px 16px' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div>
            <strong style={{ fontSize: 14 }}>SSH 凭据</strong>
            <span style={{ color: 'var(--text-secondary)', fontSize: 12, marginLeft: 8 }}>用于配置备份抓取</span>
          </div>
          <button className="btn btn-sm" onClick={() => setEditingSsh(!editingSsh)}>{editingSsh ? '取消' : '设置'}</button>
        </div>
        {editingSsh && (
          <div style={{ display: 'flex', gap: 10, marginTop: 12, alignItems: 'center', flexWrap: 'wrap' }}>
            <input className="input" placeholder="SSH 用户名" value={sshUsername}
              onChange={e => setSshUsername(e.target.value)} style={{ width: 140 }} />
            <input className="input" type="password" placeholder="SSH 密码" value={sshPassword}
              onChange={e => setSshPassword(e.target.value)} style={{ width: 140 }} />
            <input className="input no-spin" type="text" inputMode="numeric" placeholder="SSH 端口" value={sshPort}
              onChange={e => {
                const v = e.target.value.replace(/\D/g, '')
                setSshPort(v ? Math.min(65535, parseInt(v, 10)) : 0)
              }} style={{ width: 100 }} />
            <button className="btn btn-sm btn-primary" onClick={saveSsh} disabled={savingSsh}>{savingSsh ? '保存中...' : '保存'}</button>
          </div>
        )}
      </div>

      {/* 时间范围选择 */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <h2 style={{ fontSize: 18 }}>监控指标</h2>
        <div style={{ display: 'flex', gap: 4 }}>
          {[1, 3, 6, 24].map(h => (
            <button key={h} className={`btn btn-sm ${rangeHours === h ? 'btn-primary' : ''}`} onClick={() => setRangeHours(h)}>
              {h}h
            </button>
          ))}
        </div>
      </div>

      {/* 图表区域 */}
      {loading ? (
        <div style={{ textAlign: 'center', padding: 80, color: 'var(--text-secondary)' }}>加载指标数据中...</div>
      ) : metricsData.length === 0 ? (
        <div className="card" style={{ textAlign: 'center', padding: 60, color: 'var(--text-secondary)' }}>
          暂无监控数据。请确认：<br/>1. 设备 SNMP 服务正常运行<br/>2. VictoriaMetrics 已启动<br/>3. 等待至少一轮采集完成（约 1 分钟）
        </div>
      ) : (
        <div className="grid-2">
          {metricsData.map(metric => {
            const isIface = isInterfaceMetric(metric.metric_name)
            const ifaceList = getIfaceList(metric)
            const selName = selectedIface[metric.metric_name]

            return (
              <div key={metric.metric_name} className="card">
                {/* 标题行 + 接口选择器 */}
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
                  <h3 style={{ fontSize: 15, margin: 0 }}>{getMetricTitle(metric.metric_name)}</h3>

                  {/* 单选下拉框（仅接口类指标显示） */}
                  {isIface && ifaceList.length > 0 && (
                    <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                      <label style={{ fontSize: 12, color: 'var(--text-secondary)' }}>接口:</label>
                      <select
                        value={selName || ''}
                        onChange={e => {
                          const val = e.target.value
                          setSelectedIface(prev => ({ ...prev, [metric.metric_name]: val }))
                          // 持久化到 localStorage
                          const savedKey = `netops_iface_sel_${id}`
                          const saved = JSON.parse(localStorage.getItem(savedKey) || '{}')
                          saved[metric.metric_name] = val
                          localStorage.setItem(savedKey, JSON.stringify(saved))
                        }}
                        style={{
                          fontSize: 13, padding: '3px 24px 3px 8px',
                          background: 'var(--bg-secondary)', border: '1px solid var(--border-color)',
                          borderRadius: 4, color: 'var(--text-primary)', minWidth: 100,
                        }}
                      >
                        {[...ifaceList].sort((a, b) => a.localeCompare(b, undefined, { numeric: true })).map(name => (
                          <option key={name} value={name}>{name}</option>
                        ))}
                      </select>
                    </div>
                  )}
                </div>

                {(() => {
                  // 检查是否全部为 -1（设备不支持此指标）
                  const allUnsupported = metric.data.every(s => s.values.length === 0 || s.values.every(v => v.value === -1))
                  if (allUnsupported) {
                    return (
                      <div style={{ height: 320, display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#8b949e' }}>
                        该设备不支持此指标的 SNMP 采集
                      </div>
                    )
                  }
                  return <ReactECharts option={getChartOption(metric)} style={{ height: 320 }} notMerge={true} lazyUpdate={true} />
                })()}
              </div>
            )
          })}
        </div>
      )}

      <hr style={{ border: 'none', borderTop: '1px solid var(--border-color)', margin: '24px 0' }} />
      <ConfigBackupPanel deviceId={id || ''} />
    </div>
  )
}
