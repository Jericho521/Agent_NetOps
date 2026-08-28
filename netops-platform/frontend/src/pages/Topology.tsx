import { useEffect, useRef, useState, useCallback } from 'react'
import {
  fetchTopology, listRegions, updateLinkCritical,
  TopologyData, TopologyNode, TopologyLink, RegionItem,
} from '../api'

const STATUS_COLOR: Record<string, string> = {
  online: '#3fb950',
  offline: '#8b949e',
  error: '#f85149',
  unknown: '#d29922',
}
const STATUS_LABEL: Record<string, string> = {
  online: '在线',
  offline: '离线',
  error: '异常',
  unknown: '未知(未录入)',
}
const TYPE_LABEL: Record<string, string> = {
  single: '单机',
  stack: '堆叠',
  mlag: 'M-LAG',
  cluster: '集群',
  unknown: '未知',
}

const W = 900, H = 560

type LayoutMode = 'force' | 'star' | 'tree' | 'custom'

// 显示选项
interface DisplayOptions {
  showName: boolean       // 设备名称
  showPort: boolean       // 接口名称
  showLinkType: boolean   // 链路类型 (LLDP/CDP)
  showRegion: boolean     // 区域
  showSubRegion: boolean  // 子区域
}

interface SimNode extends TopologyNode {
  x: number
  y: number
  vx: number
  vy: number
  fixed?: boolean
}

export default function Topology() {
  const [data, setData] = useState<TopologyData | null>(null)
  const [loading, setLoading] = useState(true)
  const [regions, setRegions] = useState<RegionItem[]>([])
  const [regionId, setRegionId] = useState('')
  const [selected, setSelected] = useState<string | null>(null)
  const [error, setError] = useState('')
  const [contextMenu, setContextMenu] = useState<{ x: number; y: number; linkId: string } | null>(null)
  const [layout, setLayout] = useState<LayoutMode>('force')
  const [isFullscreen, setIsFullscreen] = useState(false)
  const [displayOptions, setDisplayOptions] = useState<DisplayOptions>({
    showName: true, showPort: false, showLinkType: true,
    showRegion: true, showSubRegion: false,
  })
  const [showOptionsPanel, setShowOptionsPanel] = useState(false)

  // 自定义视图：保存用户拖拽后的位置
  const customPositionsRef = useRef<Map<string, { x: number; y: number }>>(new Map())

  const containerRef = useRef<HTMLDivElement | null>(null)
  const svgRef = useRef<SVGSVGElement | null>(null)
  const nodesRef = useRef<Map<string, SimNode>>(new Map())
  const linksRef = useRef<TopologyLink[]>([])
  const animRef = useRef<number>(0)
  const draggingRef = useRef<string | null>(null)
  const [, forceRender] = useState(0)

  // 画布缩放/平移
  const [view, setView] = useState({ tx: 0, ty: 0, k: 1 })
  const panRef = useRef<{ x: number; y: number; tx: number; ty: number } | null>(null)

  async function load() {
    setLoading(true)
    setError('')
    try {
      const [topo, regs] = await Promise.all([
        fetchTopology(regionId || undefined),
        listRegions().catch(() => [] as RegionItem[]),
      ])
      setData(topo)
      setRegions(regs)
      linksRef.current = topo.links
      initLayout(topo, layout)
    } catch (e: any) {
      setError(e?.response?.data?.detail || e?.message || '加载拓扑失败')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [regionId])

  useEffect(() => {
    if (!data) return
    initLayout(data, layout)
  }, [layout])

  useEffect(() => {
    const onFsChange = () => setIsFullscreen(!!document.fullscreenElement)
    document.addEventListener('fullscreenchange', onFsChange)
    return () => document.removeEventListener('fullscreenchange', onFsChange)
  }, [])

  function toggleFullscreen() {
    const el = containerRef.current
    if (!el) return
    if (!document.fullscreenElement) {
      el.requestFullscreen().catch(() => {})
    } else {
      document.exitFullscreen().catch(() => {})
    }
  }

  function onWheel(e: React.WheelEvent) {
    e.preventDefault()
    const svg = svgRef.current!
    const rect = svg.getBoundingClientRect()
    // 鼠标在 SVG 内的坐标（未变换前）
    const mx = e.clientX - rect.left
    const my = e.clientY - rect.top
    setView(v => {
      const scale = e.deltaY < 0 ? 1.1 : 1 / 1.1
      const newK = Math.min(4, Math.max(0.2, v.k * scale))
      // 以鼠标为中心缩放：保持鼠标点对应的世界坐标不变
      const wx = (mx - v.tx) / v.k
      const wy = (my - v.ty) / v.k
      const tx = mx - wx * newK
      const ty = my - wy * newK
      return { tx, ty, k: newK }
    })
  }

  function onCanvasDown(e: React.MouseEvent) {
    // 只有点在空白处（非节点、非链路）才平移画布
    if (draggingRef.current) return
    panRef.current = { x: e.clientX, y: e.clientY, tx: view.tx, ty: view.ty }
  }
  function onCanvasMove(e: React.MouseEvent) {
    if (panRef.current) {
      const dx = e.clientX - panRef.current.x
      const dy = e.clientY - panRef.current.y
      setView(v => ({ ...v, tx: panRef.current!.tx + dx, ty: panRef.current!.ty + dy }))
      return
    }
    if (!draggingRef.current) return
    const p = svgPoint(e)
    const nd = nodesRef.current.get(draggingRef.current)
    if (nd) { nd.x = p.x; nd.y = p.y; nd.vx = 0; nd.vy = 0; forceRender(t => t + 1) }
  }
  function onCanvasUp() {
    panRef.current = null
    if (draggingRef.current) {
      const nd = nodesRef.current.get(draggingRef.current)
      if (nd) {
        nd.fixed = false
        // 保存拖拽后的位置到自定义视图
        saveCustomPosition(draggingRef.current, nd.x, nd.y)
      }
      draggingRef.current = null
    }
  }

  async function toggleLinkCritical(linkId: string) {
    const link = linksRef.current.find(l => l.id === linkId)
    if (!link) return
    try {
      await updateLinkCritical(linkId, !link.is_critical)
      link.is_critical = !link.is_critical
      forceRender(t => t + 1)
    } catch (e: any) {
      setError(e?.response?.data?.detail || e?.message || '标记失败')
    }
    setContextMenu(null)
  }

  function initLayout(topo: TopologyData, mode: LayoutMode) {
    const map = new Map<string, SimNode>()
    topo.nodes.forEach((nd, i) => {
      map.set(nd.id, { ...nd, x: W / 2, y: H / 2, vx: 0, vy: 0 })
    })
    nodesRef.current = map
    linksRef.current = topo.links

    if (mode === 'force') {
      const n = topo.nodes.length || 1
      topo.nodes.forEach((nd, i) => {
        const angle = (i / n) * Math.PI * 2
        const node = map.get(nd.id)!
        node.x = W / 2 + Math.cos(angle) * 200 + (Math.random() - 0.5) * 40
        node.y = H / 2 + Math.sin(angle) * 200 + (Math.random() - 0.5) * 40
      })
      startForceAnimation()
    } else if (mode === 'custom') {
      // 自定义视图：恢复用户拖拽保存的位置
      topo.nodes.forEach((nd, i) => {
        const node = map.get(nd.id)!
        const saved = customPositionsRef.current.get(nd.id)
        if (saved) { node.x = saved.x; node.y = saved.y }
        else { node.x = W / 2 + (Math.random() - .5) * 200; node.y = H / 2 + (Math.random() - .5) * 200 }
        node.vx = 0; node.vy = 0
      })
      forceRender(t => t + 1)
    } else if (mode === 'star') {
      applyStarLayout(map)
      forceRender(t => t + 1)
    } else if (mode === 'tree') {
      applyTreeLayout(map, topo.links)
      forceRender(t => t + 1)
    }
  }

  // 节点拖拽结束时保存位置到自定义视图
  function saveCustomPosition(id: string, x: number, y: number) {
    customPositionsRef.current.set(id, { x, y })
  }

  function applyStarLayout(map: Map<string, SimNode>) {
    const nodes = Array.from(map.values())
    // 选中心：度数最大；平手时优先 role=core 或 name 含"核心"
    const degree = new Map<string, number>()
    nodes.forEach(n => degree.set(n.id, 0))
    linksRef.current.forEach(l => {
      degree.set(l.source, (degree.get(l.source) || 0) + 1)
      degree.set(l.target, (degree.get(l.target) || 0) + 1)
    })
    const center = nodes.slice().sort((a, b) => {
      const d = (degree.get(b.id) || 0) - (degree.get(a.id) || 0)
      if (d !== 0) return d
      const aCore = (a.role === 'core' || a.name.includes('核心')) ? 1 : 0
      const bCore = (b.role === 'core' || b.name.includes('核心')) ? 1 : 0
      return bCore - aCore
    })[0]

    const others = nodes.filter(n => n.id !== center.id)
    center.x = W / 2
    center.y = H / 2
    const radius = Math.min(W, H) * 0.38
    others.forEach((n, i) => {
      const angle = (i / Math.max(1, others.length)) * Math.PI * 2 - Math.PI / 2
      n.x = W / 2 + Math.cos(angle) * radius
      n.y = H / 2 + Math.sin(angle) * radius
    })
  }

  function applyTreeLayout(map: Map<string, SimNode>, links: TopologyLink[]) {
    const nodes = Array.from(map.values())
    // 选根：度数最大且 role=core/核心
    const degree = new Map<string, number>()
    nodes.forEach(n => degree.set(n.id, 0))
    links.forEach(l => {
      degree.set(l.source, (degree.get(l.source) || 0) + 1)
      degree.set(l.target, (degree.get(l.target) || 0) + 1)
    })
    const root = nodes.slice().sort((a, b) => {
      const d = (degree.get(b.id) || 0) - (degree.get(a.id) || 0)
      if (d !== 0) return d
      const aCore = (a.role === 'core' || a.name.includes('核心')) ? 1 : 0
      const bCore = (b.role === 'core' || b.name.includes('核心')) ? 1 : 0
      return bCore - aCore
    })[0]

    // BFS 分层
    const adj = new Map<string, string[]>()
    nodes.forEach(n => adj.set(n.id, []))
    links.forEach(l => {
      if (!adj.get(l.source)!.includes(l.target)) adj.get(l.source)!.push(l.target)
      if (!adj.get(l.target)!.includes(l.source)) adj.get(l.target)!.push(l.source)
    })

    const visited = new Set<string>([root.id])
    const levels: string[][] = [[root.id]]
    let current = [root.id]
    while (current.length) {
      const next: string[] = []
      current.forEach(id => {
        adj.get(id)!.forEach(nb => {
          if (!visited.has(nb)) {
            visited.add(nb)
            next.push(nb)
          }
        })
      })
      if (next.length) levels.push(next)
      current = next
    }

    const levelHeight = Math.min(120, (H - 100) / Math.max(1, levels.length))
    levels.forEach((level, li) => {
      const y = 60 + li * levelHeight
      const gap = (W - 120) / Math.max(1, level.length)
      level.forEach((id, i) => {
        const node = map.get(id)
        if (node) {
          node.x = 60 + (i + 0.5) * gap
          node.y = y
        }
      })
    })
  }

  const startForceAnimation = useCallback(() => {
    cancelAnimationFrame(animRef.current)
    let ticks = 0
    const step = () => {
      const nodes = Array.from(nodesRef.current.values())
      for (let i = 0; i < nodes.length; i++) {
        for (let j = i + 1; j < nodes.length; j++) {
          const a = nodes[i], b = nodes[j]
          let dx = a.x - b.x, dy = a.y - b.y
          let dist2 = dx * dx + dy * dy
          if (dist2 < 0.01) { dx = Math.random(); dy = Math.random(); dist2 = 1 }
          const dist = Math.sqrt(dist2)
          const force = 6000 / dist2
          const fx = (dx / dist) * force, fy = (dy / dist) * force
          if (!a.fixed) { a.vx += fx; a.vy += fy }
          if (!b.fixed) { b.vx -= fx; b.vy -= fy }
        }
      }
      for (const lk of linksRef.current) {
        const a = nodesRef.current.get(lk.source)
        const b = nodesRef.current.get(lk.target)
        if (!a || !b) continue
        const dx = b.x - a.x, dy = b.y - a.y
        const dist = Math.sqrt(dx * dx + dy * dy) || 1
        const target = 120
        const k = 0.02
        const force = (dist - target) * k
        const fx = (dx / dist) * force, fy = (dy / dist) * force
        if (!a.fixed) { a.vx += fx; a.vy += fy }
        if (!b.fixed) { b.vx -= fx; b.vy -= fy }
      }
      for (const nd of nodes) {
        if (nd.fixed) { nd.vx = 0; nd.vy = 0; continue }
        nd.vx += (W / 2 - nd.x) * 0.002
        nd.vy += (H / 2 - nd.y) * 0.002
        nd.vx *= 0.85; nd.vy *= 0.85
        nd.x += nd.vx; nd.y += nd.vy
        nd.x = Math.max(40, Math.min(W - 40, nd.x))
        nd.y = Math.max(40, Math.min(H - 40, nd.y))
      }
      ticks++
      forceRender(t => t + 1)
      if (ticks < 300) animRef.current = requestAnimationFrame(step)
    }
    animRef.current = requestAnimationFrame(step)
  }, [])

  useEffect(() => () => cancelAnimationFrame(animRef.current), [])

  function svgPoint(e: React.MouseEvent) {
    const svg = svgRef.current!
    const rect = svg.getBoundingClientRect()
    const scaleX = W / rect.width
    const scaleY = H / rect.height
    const screenX = (e.clientX - rect.left) * scaleX
    const screenY = (e.clientY - rect.top) * scaleY
    // 反变换 view 的 translate/scale，得到世界坐标
    return { x: (screenX - view.tx) / view.k, y: (screenY - view.ty) / view.k }
  }
  function onNodeDown(e: React.MouseEvent, id: string) {
    e.stopPropagation()
    draggingRef.current = id
    const nd = nodesRef.current.get(id)
    if (nd) nd.fixed = true
  }

  const nodes = data ? Array.from(nodesRef.current.values()) : []
  const selectedNode = selected ? nodesRef.current.get(selected) : null
  const neighbors = selected
    ? new Set(linksRef.current.filter(l => l.source === selected || l.target === selected).flatMap(l => [l.source, l.target]))
    : null

  const LayoutButton = ({ mode, label }: { mode: LayoutMode; label: string }) => (
    <button
      className="btn"
      style={{
        padding: '4px 10px', fontSize: 12,
        background: layout === mode ? 'var(--accent)' : undefined,
        color: layout === mode ? '#fff' : undefined,
      }}
      onClick={() => setLayout(mode)}
    >{label}</button>
  )

  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
        <div>
          <h1 style={{ fontSize: 20, fontWeight: 700 }}>拓扑管理</h1>
          <p style={{ fontSize: 13, color: 'var(--text-secondary)', marginTop: 4 }}>
            基于 LLDP/CDP 自动发现设备连接关系
          </p>
        </div>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center', position: 'relative' }}>
          <select className="input" style={{ width: 160 }} value={regionId} onChange={e => setRegionId(e.target.value)}>
            <option value="">全部区域</option>
            {regions.map(r => (
              <option key={r.id} value={r.id}>{r.name}</option>
            ))}
          </select>
          <LayoutButton mode="force" label="力导向" />
          <LayoutButton mode="star" label="星型" />
          <LayoutButton mode="tree" label="树形" />
          <LayoutButton mode="custom" label="自定义" />
          <span style={{ position: 'relative' }}>
            <button className="btn" onClick={() => setShowOptionsPanel(v => !v)} title="显示选项">
              ⚙ 显示
            </button>
            {showOptionsPanel && (
              <div style={{
                position: 'absolute', top: '100%', right: 0, marginTop: 4,
                background: 'var(--bg-primary)', border: '1px solid var(--border-color)',
                borderRadius: 8, padding: 10, zIndex: 1000, minWidth: 160,
                boxShadow: '0 4px 12px rgba(0,0,0,0.15)',
              }}>
                {([
                  ['showName', '设备名称'],
                  ['showPort', '接口名称'],
                  ['showLinkType', '链路类型'],
                  ['showRegion', '区域'],
                  ['showSubRegion', '子区域'],
                ] as const).map(([key, label]) => (
                  <label key={key} style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12, marginBottom: 4, cursor: 'pointer' }}>
                    <input
                      type="checkbox"
                      checked={displayOptions[key]}
                      onChange={e => setDisplayOptions(prev => ({ ...prev, [key]: e.target.checked }))}
                    />
                    {label}
                  </label>
                ))}
              </div>
            )}
          </span>
          <button className="btn" onClick={toggleFullscreen}>
            {isFullscreen ? '退出全屏' : '⛶ 全屏'}
          </button>
          <button className="btn" onClick={() => setView({ tx: 0, ty: 0, k: 1 })} title="重置缩放/平移">
            🔍 重置视图
          </button>
          <button className="btn" onClick={load} disabled={loading}>
            {loading ? '刷新中…' : '🔄 刷新'}
          </button>
        </div>
      </div>

      {error && <div className="alert-error" style={{ marginBottom: 12 }}>{error}</div>}

      <div style={{ display: 'flex', gap: 16, alignItems: 'flex-start' }}>
        <div
          ref={containerRef}
          style={{
            flex: 1, background: 'var(--bg-secondary)', borderRadius: 10,
            border: '1px solid var(--border-color)', overflow: 'hidden', position: 'relative',
            height: isFullscreen ? '100vh' : undefined,
            ...(isFullscreen ? {
              position: 'fixed', inset: 0, width: '100vw', height: '100vh',
              zIndex: 9999, borderRadius: 0, border: 'none',
            } : {}),
          }}
        >
          <svg
            ref={svgRef}
            viewBox={`0 0 ${W} ${H}`}
            preserveAspectRatio="xMidYMid meet"
            style={{ width: '100%', height: isFullscreen ? '100%' : 560, display: 'block', cursor: panRef.current ? 'grabbing' : 'grab' }}
            onWheel={onWheel}
            onMouseDown={onCanvasDown}
            onMouseMove={onCanvasMove}
            onMouseUp={onCanvasUp}
            onMouseLeave={onCanvasUp}
            onClick={() => { setSelected(null); setContextMenu(null) }}
          >
            <g transform={`translate(${view.tx},${view.ty}) scale(${view.k})`}>
            {/* 连线（聚合合并：同 source+target 合并为一条） */}
            {(() => {
              // 按 source+target 分组
              const groups = new Map<string, TopologyLink[]>()
              for (const lk of linksRef.current) {
                const key = lk.source < lk.target ? `${lk.source}|${lk.target}` : `${lk.target}|${lk.source}`
                if (!groups.has(key)) groups.set(key, [])
                groups.get(key)!.push(lk)
              }
              return Array.from(groups.entries()).map(([key, group]) => {
                const lk = group[0]
                const a = nodesRef.current.get(lk.source)
                const b = nodesRef.current.get(lk.target)
                if (!a || !b) return null
                const dim = neighbors ? !(neighbors.has(lk.source) && neighbors.has(lk.target)) : false
                const isCritical = group.some(l => l.is_critical)
                const isLag = group.length > 1 || group.some(l => l.link_type === 'lag')
                const color = isCritical ? '#f85149' : (lk.protocol === 'cdp' ? '#fb8500' : '#58a6ff')
                const width = isLag ? Math.min(5, 1.5 + group.length * 0.6) : (isCritical ? 3 : 1.5)
                return (
                  <g key={key}>
                    <line
                      x1={a.x} y1={a.y} x2={b.x} y2={b.y}
                      stroke={dim ? 'var(--border-color)' : color}
                      strokeWidth={width}
                      strokeOpacity={dim ? 0.25 : (isCritical ? 1 : 0.7)}
                      style={{ cursor: 'context-menu' }}
                      onContextMenu={e => {
                        e.preventDefault()
                        setContextMenu({ x: e.clientX, y: e.clientY, linkId: lk.id })
                      }}
                    />
                    {isLag && (
                      <text
                        x={(a.x + b.x) / 2} y={(a.y + b.y) / 2 - (displayOptions.showLinkType ? 14 : 8)}
                        textAnchor="middle" fontSize={10} fill={color}
                        style={{ pointerEvents: 'none', userSelect: 'none' }}
                      >LAG ×{group.length}</text>
                    )}
                    {displayOptions.showLinkType && !isLag && (
                      <text
                        x={(a.x + b.x) / 2} y={(a.y + b.y) / 2 - 6}
                        textAnchor="middle" fontSize={9} fill={color}
                        style={{ pointerEvents: 'none', userSelect: 'none' }}
                      >{(lk.protocol || '').toUpperCase()}</text>
                    )}
                    {displayOptions.showPort && group.length === 1 && lk.local_port && (
                      <text
                        x={(a.x + b.x) / 2} y={(a.y + b.y) / 2 + 12}
                        textAnchor="middle" fontSize={8} fill="var(--text-secondary)"
                        style={{ pointerEvents: 'none', userSelect: 'none' }}
                      >{lk.local_port.length > 20 ? lk.local_port.slice(0, 20) + '..' : lk.local_port}</text>
                    )}
                    {isCritical && !isLag && (
                      <text
                        x={(a.x + b.x) / 2} y={(a.y + b.y) / 2 - 6}
                        textAnchor="middle" fontSize={12} fill="#f85149"
                        style={{ pointerEvents: 'none', userSelect: 'none' }}
                      >★</text>
                    )}
                  </g>
                )
              })
            })()}
            {/* 节点 */}
            {nodes.map(nd => (
              <NodeShape
                key={nd.id}
                node={nd}
                dim={neighbors ? !neighbors.has(nd.id) : false}
                selected={selected === nd.id}
                onMouseDown={e => onNodeDown(e, nd.id)}
                onClick={e => { e.stopPropagation(); setSelected(nd.id) }}
                displayOptions={displayOptions}
              />
            ))}
            </g>
          </svg>

          {/* 图例 */}
          <div style={{
            position: 'absolute', left: 12, bottom: 12, fontSize: 12,
            background: 'var(--bg-primary)', padding: '8px 10px', borderRadius: 8,
            border: '1px solid var(--border-color)', lineHeight: 1.8,
          }}>
            <div style={{ fontWeight: 600, marginBottom: 4 }}>图例</div>
            {Object.entries(STATUS_LABEL).map(([k, v]) => (
              <div key={k} style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                <span style={{
                  width: 10, height: 10, borderRadius: '50%',
                  background: STATUS_COLOR[k], display: 'inline-block',
                  border: k === 'unknown' ? '2px dashed #d29922' : undefined,
                }} />
                {v}
              </div>
            ))}
            <div style={{ marginTop: 6, fontWeight: 600 }}>网元类型</div>
            {Object.entries(TYPE_LABEL).filter(([k]) => k !== 'unknown').map(([k, v]) => (
              <div key={k} style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                <NodeLegendIcon type={k} />
                {v}
              </div>
            ))}
            <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginTop: 4 }}>
              <span style={{ width: 18, height: 3, background: '#f85149', display: 'inline-block' }} />
              重要链路
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginTop: 4 }}>
              <span style={{ width: 18, height: 4, background: '#58a6ff', display: 'inline-block', borderRadius: 2 }} />
              聚合链路 (LAG)
            </div>
          </div>

          {/* 右键菜单 */}
          {contextMenu && (
            <div
              style={{
                position: 'fixed', left: contextMenu.x, top: contextMenu.y,
                background: 'var(--bg-primary)', border: '1px solid var(--border-color)',
                borderRadius: 6, padding: '6px 0', zIndex: 1000, minWidth: 140,
                boxShadow: '0 4px 12px rgba(0,0,0,0.15)',
              }}
              onMouseLeave={() => setContextMenu(null)}
            >
              <button
                className="btn-link"
                style={{ display: 'block', width: '100%', textAlign: 'left', padding: '6px 12px', border: 'none', background: 'none', color: 'var(--text-primary)', cursor: 'pointer' }}
                onClick={() => toggleLinkCritical(contextMenu.linkId)}
              >
                {linksRef.current.find(l => l.id === contextMenu.linkId)?.is_critical ? '取消重要链路' : '标记为重要链路'}
              </button>
            </div>
          )}
        </div>

        {/* 详情面板 */}
        <div style={{ width: 260, flexShrink: 0, display: isFullscreen ? 'none' : 'block' }}>
          <div style={{
            background: 'var(--bg-secondary)', borderRadius: 10,
            border: '1px solid var(--border-color)', padding: 16,
          }}>
            <h3 style={{ fontSize: 14, fontWeight: 600, marginBottom: 12 }}>统计</h3>
            {data && (
              <div style={{ fontSize: 13, lineHeight: 2 }}>
                <div>设备节点：<b>{data.stats.node_count}</b></div>
                <div>连接链路：<b>{data.stats.link_count}</b></div>
                <div>重要链路：<b>{data.stats.critical_count ?? 0}</b></div>
                <div>未录入对端：<b>{data.stats.virtual_count}</b></div>
              </div>
            )}
          </div>

          {selectedNode && (
            <div style={{
              background: 'var(--bg-secondary)', borderRadius: 10,
              border: '1px solid var(--border-color)', padding: 16,
              marginTop: 12,
            }}>
              <h3 style={{ fontSize: 14, fontWeight: 600, marginBottom: 10 }}>设备详情</h3>
              <div style={{ fontSize: 13, lineHeight: 1.9 }}>
                <div><span style={{ color: 'var(--text-secondary)' }}>名称：</span>{selectedNode.name}</div>
                {selectedNode.sys_name && <div><span style={{ color: 'var(--text-secondary)' }}>系统名：</span>{selectedNode.sys_name}</div>}
                <div><span style={{ color: 'var(--text-secondary)' }}>网元类型：</span>{TYPE_LABEL[selectedNode.device_type || 'single'] || selectedNode.device_type}</div>
                <div><span style={{ color: 'var(--text-secondary)' }}>IP：</span>{selectedNode.ip || '-'}</div>
                {selectedNode.aliases && selectedNode.aliases.length > 0 && (
                  <div>
                    <span style={{ color: 'var(--text-secondary)' }}>别名/成员：</span>
                    {selectedNode.aliases.map(a => a.ip).join(', ')}
                  </div>
                )}
                <div><span style={{ color: 'var(--text-secondary)' }}>厂商：</span>{selectedNode.vendor || '-'}</div>
                <div><span style={{ color: 'var(--text-secondary)' }}>型号：</span>{selectedNode.model || '-'}</div>
                <div><span style={{ color: 'var(--text-secondary)' }}>角色：</span>{selectedNode.role || '-'}</div>
                <div><span style={{ color: 'var(--text-secondary)' }}>状态：</span>{STATUS_LABEL[selectedNode.status] || selectedNode.status}</div>
              </div>
              <div style={{ marginTop: 10, borderTop: '1px solid var(--border-color)', paddingTop: 10 }}>
                <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginBottom: 6 }}>连接端口</div>
                {linksRef.current
                  .filter(l => l.source === selected || l.target === selected)
                  .map(l => {
                    const isSrc = l.source === selected
                    const other = isSrc ? l.target : l.source
                    const otherNode = nodesRef.current.get(other)
                    return (
                      <div key={l.id} style={{ fontSize: 12, marginBottom: 4, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                        <span>
                          <span style={{ color: STATUS_COLOR[l.protocol === 'cdp' ? 'offline' : 'online'] }}>
                            {l.protocol.toUpperCase()}
                          </span>{' '}
                          {isSrc ? l.local_port : l.remote_port} → {otherNode?.name || (isSrc ? l.remote_sysname : '-')}
                          {isSrc ? ` :${l.remote_port || ''}` : ''}
                        </span>
                        <button
                          title={l.is_critical ? '取消重要链路' : '标记为重要链路'}
                          onClick={() => toggleLinkCritical(l.id)}
                          style={{ border: 'none', background: 'none', cursor: 'pointer', color: l.is_critical ? '#f85149' : 'var(--text-secondary)', fontSize: 13 }}
                        >
                          {l.is_critical ? '★' : '☆'}
                        </button>
                      </div>
                    )
                  })}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

function NodeShape({
  node,
  dim,
  selected,
  onMouseDown,
  onClick,
  displayOptions,
}: {
  node: SimNode
  dim: boolean
  selected: boolean
  onMouseDown: (e: React.MouseEvent) => void
  onClick: (e: React.MouseEvent) => void
  displayOptions: DisplayOptions
}) {
  const color = STATUS_COLOR[node.status] || '#8b949e'
  const type = node.virtual ? 'unknown' : (node.device_type || 'single')
  const r = selected ? 18 : 14
  const stroke = selected ? '#fff' : color
  const fill = node.virtual ? 'transparent' : color
  const common = {
    fill,
    stroke,
    strokeWidth: selected ? 3 : 2,
    style: { cursor: 'pointer' },
  }

  let shape: JSX.Element
  switch (type) {
    case 'stack':
      shape = <rect x={-r} y={-r * 0.8} width={r * 2} height={r * 1.6} rx={4} {...common} />
      break
    case 'mlag':
      shape = <polygon points={`0,-${r} ${r},0 0,${r} -${r},0`} {...common} />
      break
    case 'cluster':
      shape = (
        <polygon
          points={[
            `0,-${r}`,
            `${r * 0.87},-${r * 0.5}`,
            `${r * 0.87},${r * 0.5}`,
            `0,${r}`,
            `-${r * 0.87},${r * 0.5}`,
            `-${r * 0.87},-${r * 0.5}`,
          ].join(' ')}
          strokeDasharray={node.virtual ? '4 3' : undefined}
          {...common}
        />
      )
      break
    case 'unknown':
      shape = <circle r={r} strokeDasharray="4 3" {...common} />
      break
    case 'single':
    default:
      shape = <circle r={r} {...common} />
  }

  return (
    <g
      transform={`translate(${node.x},${node.y})`}
      style={{ cursor: 'pointer', opacity: dim ? 0.3 : 1 }}
      onMouseDown={onMouseDown}
      onClick={onClick}
    >
      {shape}
      {/* 设备名称 */}
      {displayOptions.showName && (
        <text
          y={r + 16} textAnchor="middle"
          fontSize={11} fill="var(--text-primary)"
          style={{ pointerEvents: 'none', userSelect: 'none' }}
        >
          {node.name?.length > 16 ? node.name.slice(0, 16) + '…' : node.name}
        </text>
      )}
      {/* 网元类型标签 */}
      {type !== 'single' && type !== 'unknown' && displayOptions.showName && (
        <text
          y={r + (displayOptions.showRegion || displayOptions.showSubRegion ? 27 : 28)} textAnchor="middle"
          fontSize={9} fill={color}
          style={{ pointerEvents: 'none', userSelect: 'none', opacity: 0.8 }}
        >
          {TYPE_LABEL[type] || type}
        </text>
      )}
      {/* 区域 */}
      {displayOptions.showRegion && node.region_name && (
        <text
          y={r + (displayOptions.showName ? 29 : 15) + (type !== 'single' ? 10 : 0)} textAnchor="middle"
          fontSize={8} fill="#a5d6ff"
          style={{ pointerEvents: 'none', userSelect: 'none', opacity: 0.7 }}
        >
          {node.region_name.length > 12 ? node.region_name.slice(0, 12) + '..' : node.region_name}
        </text>
      )}
      {/* 子区域 */}
      {displayOptions.showSubRegion && node.sub_region_name && (
        <text
          y={r + (displayOptions.showName ? 39 : 25) + (type !== 'single' ? 10 : 0) + (displayOptions.showRegion ? 9 : 0)} textAnchor="middle"
          fontSize={7.5} fill="#79c0ff"
          style={{ pointerEvents: 'none', userSelect: 'none', opacity: 0.6 }}
        >
          {node.sub_region_name.length > 14 ? node.sub_region_name.slice(0, 14) + '..' : node.sub_region_name}
        </text>
      )}
    </g>
  )
}

function NodeLegendIcon({ type }: { type: string }) {
  const color = '#8b949e'
  const r = 6
  const common = { fill: 'transparent', stroke: color, strokeWidth: 1.5 }
  switch (type) {
    case 'stack':
      return <svg width={14} height={12}><rect x={1} y={1} width={12} height={10} rx={2} {...common} /></svg>
    case 'mlag':
      return <svg width={14} height={12}><polygon points="7,1 13,6 7,11 1,6" {...common} /></svg>
    case 'cluster':
      return <svg width={14} height={12}><polygon points="7,1 12,4 12,8 7,11 2,8 2,4" {...common} /></svg>
    default:
      return <svg width={14} height={12}><circle cx={7} cy={6} r={5} {...common} /></svg>
  }
}
