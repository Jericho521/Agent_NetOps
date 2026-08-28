import { Routes, Route, Navigate } from 'react-router-dom'
import { getUser } from './api'
import Layout from './components/Layout'
import Login from './pages/Login'
import Dashboard from './pages/Dashboard'
import DeviceList from './pages/DeviceList'
import DeviceDetail from './pages/DeviceDetail'
import Alerts from './pages/Alerts'
import AlertRules from './pages/AlertRules'
import Traps from './pages/Traps'
import AIAssistant from './pages/AIAssistant'
import ReportCenter from './pages/ReportCenter'
import RegionManager from './pages/RegionManager'
import Topology from './pages/Topology'

function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/" element={<RequireAuth><Layout /></RequireAuth>}>
        <Route index element={<Dashboard />} />
        <Route path="devices" element={<DeviceList />} />
        <Route path="devices/:id" element={<DeviceDetail />} />
        <Route path="alerts" element={<Alerts />} />
        <Route path="alerts/rules" element={<AlertRules />} />
        <Route path="traps" element={<Traps />} />
        <Route path="ai" element={<AIAssistant />} />
        <Route path="reports" element={<ReportCenter />} />
        <Route path="regions" element={<RegionManager />} />
        <Route path="topology" element={<Topology />} />
      </Route>
    </Routes>
  )
}

/** 路由守卫：未登录跳转 /login */
function RequireAuth({ children }: { children: React.ReactNode }) {
  const user = getUser()
  if (!user) {
    return <Navigate to="/login" replace />
  }
  return <>{children}</>
}

export default App
