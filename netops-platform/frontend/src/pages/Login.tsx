import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { login } from '../api'

export default function Login() {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const navigate = useNavigate()

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError('')
    setLoading(true)

    try {
      await login(username, password)
      navigate('/')
    } catch (err: any) {
      setError(err.response?.data?.detail || '登录失败，请检查用户名和密码')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div style={styles.container}>
      {/* ===== 左侧：品牌展示区 ===== */}
      <div style={styles.leftPanel}>
        {/* 装饰性背景元素 */}
        <div style={styles.bgDot1} />
        <div style={styles.bgDot2} />
        <div style={styles.bgCube1} />
        <div style={styles.bgCube2} />
        <div style={styles.bgCube3} />

        <div style={styles.leftContent}>
          <h1 style={styles.brandTitle}>网络 AI 运维监控平台</h1>
          <p style={styles.brandDesc}>
            基于 SNMP + LLDP 的网络设备自动化运维平台。支持设备批量纳管、拓扑自动发现、
            实时指标采集、告警智能分析、链路可视化追踪。让网络运维从被动救火转向主动感知，
            用 AI 赋能网络管理，实现故障秒级定位、变更可追溯、资产全生命周期管控。
          </p>
          <div style={styles.featureTags}>
            <span className="feature-tag">SNMP 自动发现</span>
            <span className="feature-tag">LLDP 拓扑生成</span>
            <span className="feature-tag">实时指标监控</span>
            <span className="feature-tag">AI 智能分析</span>
          </div>
        </div>
      </div>

      {/* ===== 右侧：登录表单区 ===== */}
      <div style={styles.rightPanel}>
        <div style={styles.formCard}>
          {/* Logo */}
          <div style={styles.logoArea}>
            <img src="/logo-512.png" alt="NetOps" style={styles.logoImg} />
          </div>
          <h2 style={styles.formTitle}>网络 AI 运维监控平台</h2>
          <p style={styles.formSubtitle}>运维监控中心</p>

          <form onSubmit={handleSubmit} style={styles.form}>
            {error && (
              <div style={styles.errorBox}>{error}</div>
            )}

            <div style={styles.fieldGroup}>
              <label style={styles.label}>用户名</label>
              <input
                style={styles.input}
                type="text"
                value={username}
                onChange={e => setUsername(e.target.value)}
                placeholder="请输入用户名"
                required
              />
            </div>

            <div style={styles.fieldGroup}>
              <label style={styles.label}>密码</label>
              <input
                style={styles.input}
                type="password"
                value={password}
                onChange={e => setPassword(e.target.value)}
                placeholder="请输入密码"
                required
              />
            </div>

            <button
              type="submit"
              disabled={loading}
              style={{
                ...styles.submitBtn,
                opacity: loading ? 0.7 : 1,
                cursor: loading ? 'not-allowed' : 'pointer',
              }}
            >
              {loading ? '登录中...' : '登 录'}
            </button>

            <p style={styles.hintText}>默认账号: admin / admin123</p>
          </form>
        </div>
      </div>
    </div>
  )
}

/* ========== 样式常量 ========== */
const s = (v: number | string) => v

const styles: Record<string, React.CSSProperties> = {
  container: {
    display: 'flex',
    minHeight: '100vh',
    width: '100%',
  },

  /* ---- 左侧面板 ---- */
  leftPanel: {
    flex: '0 0 55%',
    background: 'linear-gradient(135deg, #0a1628 0%, #102a43 50%, #0d3b66 100%)',
    position: 'relative' as const,
    overflow: 'hidden' as const,
    display: 'flex',
    alignItems: 'center',
    padding: '60px 80px',
  },
  bgDot1: {
    position: 'absolute' as const,
    top: '8%',
    right: '15%',
    width: 120,
    height: 120,
    backgroundImage: 'radial-gradient(circle, rgba(88,166,255,0.15) 2px, transparent 2px)',
    backgroundSize: '16px 16px',
    borderRadius: '50%',
  },
  bgDot2: {
    position: 'absolute' as const,
    bottom: '15%',
    right: '35%',
    width: 80,
    height: 80,
    backgroundImage: 'radial-gradient(circle, rgba(88,166,255,0.12) 2px, transparent 2px)',
    backgroundSize: '12px 12px',
    borderRadius: '50%',
  },
  bgCube1: {
    position: 'absolute' as const,
    bottom: '12%',
    right: '10%',
    width: 100,
    height: 40,
    background: 'linear-gradient(135deg, rgba(88,166,255,0.25), rgba(13,59,102,0.4))',
    borderRadius: 6,
    transform: 'perspective(200px) rotateX(15deg) rotateY(-5deg)',
  },
  bgCube2: {
    position: 'absolute' as const,
    top: '18%',
    right: '5%',
    width: 70,
    height: 28,
    background: 'linear-gradient(135deg, rgba(63,185,80,0.2), rgba(13,59,102,0.3))',
    borderRadius: 6,
    transform: 'perspective(200px) rotateX(20deg) rotateY(-10deg)',
  },
  bgCube3: {
    position: 'absolute' as const,
    bottom: '38%',
    right: '25%',
    width: 56,
    height: 22,
    background: 'linear-gradient(135deg, rgba(88,166,255,0.15), rgba(13,59,102,0.25))',
    borderRadius: 4,
    transform: 'perspective(180px) rotateX(12deg) rotateY(-8deg)',
  },
  leftContent: {
    position: 'relative' as const,
    zIndex: 1,
    maxWidth: 520,
  },
  brandTitle: {
    fontSize: 36,
    fontWeight: 800,
    color: '#ffffff',
    marginBottom: 24,
    letterSpacing: 1,
  },
  brandDesc: {
    fontSize: 14,
    lineHeight: 1.9,
    color: 'rgba(230,237,243,0.75)',
    marginBottom: 32,
  },
  featureTags: {
    display: 'flex',
    flexWrap: 'wrap' as const,
    gap: 10,
  },

  /* ---- 右侧面板 ---- */
  rightPanel: {
    flex: 1,
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    background: '#f5f7fa',
    padding: 40,
  },
  formCard: {
    width: '100%',
    maxWidth: 400,
    textAlign: 'center' as const,
  },
  logoArea: {
    marginBottom: 16,
  },
  logoImg: {
    width: 72,
    height: 72,
    objectFit: 'contain' as const,
  },
  formTitle: {
    fontSize: 20,
    fontWeight: 700,
    color: '#1f2328',
    marginBottom: 4,
  },
  formSubtitle: {
    fontSize: 13,
    color: '#656d76',
    marginBottom: 36,
  },
  form: {
    textAlign: 'left' as const,
  },
  fieldGroup: {
    marginBottom: 20,
  },
  label: {
    display: 'block',
    fontSize: 13,
    color: '#656d76',
    marginBottom: 6,
    fontWeight: 500,
  },
  input: {
    width: '100%',
    padding: '10px 14px',
    border: '1px solid #d0d7de',
    borderRadius: 8,
    fontSize: 14,
    outline: 'none',
    transition: 'border-color 0.2s',
    background: '#ffffff',
    color: '#1f2328',
    boxSizing: 'border-box' as const,
  },
  errorBox: {
    background: 'rgba(248,81,73,0.08)',
    border: '1px solid #cf222e',
    borderRadius: 8,
    padding: '10px 14px',
    marginBottom: 16,
    color: '#cf222e',
    fontSize: 13,
  },
  submitBtn: {
    width: '100%',
    padding: '11px',
    border: 'none',
    borderRadius: 8,
    background: '#0969da',
    color: '#ffffff',
    fontSize: 15,
    fontWeight: 600,
    marginTop: 4,
    transition: 'opacity 0.2s',
  },
  hintText: {
    textAlign: 'center' as const,
    marginTop: 16,
    fontSize: 12,
    color: '#8b949e',
  },
}
