import { Outlet, NavLink, useNavigate } from 'react-router-dom'
import { useState, useEffect } from 'react'
import { getUser, clearAuth } from '../api'

const THEME_KEY = 'netops_theme'

type Theme = 'dark' | 'light'

function getSavedTheme(): Theme {
  const saved = localStorage.getItem(THEME_KEY)
  if (saved === 'light' || saved === 'dark') return saved
  return window.matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark'
}

export default function Layout() {
  const user = getUser()
  const navigate = useNavigate()
  const [theme, setTheme] = useState<Theme>('dark')

  useEffect(() => {
    const initial = getSavedTheme()
    setTheme(initial)
    document.body.setAttribute('data-theme', initial)
  }, [])

  function toggleTheme() {
    const next = theme === 'dark' ? 'light' : 'dark'
    setTheme(next)
    localStorage.setItem(THEME_KEY, next)
    document.body.setAttribute('data-theme', next)
  }

  function handleLogout() {
    clearAuth()
    navigate('/login')
  }

  return (
    <div style={{ display: 'flex', minHeight: '100vh' }}>
      {/* 侧边栏 */}
      <aside style={{
        width: 220,
        background: 'var(--bg-secondary)',
        borderRight: '1px solid var(--border-color)',
        padding: '20px 12px',
        display: 'flex',
        flexDirection: 'column',
      }}>
        {/* Logo */}
        <div style={{ marginBottom: 32, paddingLeft: 8 }}>
          <h2 style={{ fontSize: 18, fontWeight: 700, color: 'var(--accent-blue)' }}>
            NetOps
          </h2>
          <p style={{ fontSize: 12, color: 'var(--text-secondary)', marginTop: 4 }}>
            网络运维监控平台
          </p>
        </div>

        {/* 导航 */}
        <nav style={{ flex: 1 }}>
          <SidebarLink to="/" icon="🏠">仪表盘</SidebarLink>
          <SidebarLink to="/devices" icon="📡">设备管理</SidebarLink>
          <SidebarLink to="/alerts" icon="🔔">告警中心</SidebarLink>
          <SidebarLink to="/alerts/rules" icon="⚙️">告警规则</SidebarLink>
          <SidebarLink to="/traps" icon="📡">SNMP Trap</SidebarLink>
          <SidebarLink to="/ai" icon="🤖">AI 助手</SidebarLink>
          <SidebarLink to="/reports" icon="📄">报表中心</SidebarLink>
          <SidebarLink to="/regions" icon="🗺️">区域管理</SidebarLink>
          <SidebarLink to="/topology" icon="🔗">拓扑管理</SidebarLink>
        </nav>

        {/* 用户信息 */}
        <div style={{ borderTop: '1px solid var(--border-color)', paddingTop: 16, fontSize: 13 }}>
          <div style={{ color: 'var(--text-secondary)', marginBottom: 8 }}>
            {user?.username} ({user?.role})
          </div>
          <button className="btn btn-sm" onClick={handleLogout} style={{ width: '100%' }}>
            退出登录
          </button>
        </div>
      </aside>

      {/* 主内容区 */}
      <main style={{ flex: 1, overflowY: 'auto' }}>
        {/* 顶部栏 */}
        <header style={{
          height: 56,
          borderBottom: '1px solid var(--border-color)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: '0 24px',
          background: 'var(--bg-secondary)',
        }}>
          <span style={{ fontWeight: 600 }}>网络 AI 运维监控平台</span>
          <button
            className="btn btn-sm"
            onClick={toggleTheme}
            title={theme === 'dark' ? '切换浅色模式' : '切换深色模式'}
            style={{ display: 'flex', alignItems: 'center', gap: 6 }}
          >
            <span>{theme === 'dark' ? '🌙' : '☀️'}</span>
            <span>{theme === 'dark' ? '深色' : '浅色'}</span>
          </button>
        </header>

        {/* 页面内容 */}
        <div className="container" style={{ paddingTop: 24 }}>
          <Outlet />
        </div>
      </main>
    </div>
  )
}

function SidebarLink({ to, icon, children }: { to: string; icon?: string; children: React.ReactNode }) {
  return (
    <NavLink
      to={to}
      style={({ isActive }) => ({
        display: 'flex',
        alignItems: 'center',
        gap: 10,
        padding: '10px 12px',
        borderRadius: 6,
        color: isActive ? 'var(--accent-blue)' : 'var(--text-primary)',
        background: isActive ? 'rgba(88, 166, 255, 0.12)' : 'transparent',
        textDecoration: 'none',
        fontSize: 14,
        marginBottom: 2,
        fontWeight: isActive ? 600 : 400,
        transition: 'all 0.2s',
      })}
    >
      <span>{icon}</span>
      {children}
    </NavLink>
  )
}
