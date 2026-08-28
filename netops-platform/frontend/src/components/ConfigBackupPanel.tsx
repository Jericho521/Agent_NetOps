import { useState, useEffect, useCallback } from 'react'
import {
  fetchConfigBackups, createConfigBackup, fetchConfigBackupContent,
  fetchConfigDiff, previewCurrentConfig, ConfigBackup,
} from '../api'

function fmtTimeCN(dateStr: string | null): string {
  if (!dateStr) return '-'
  let d = new Date(dateStr)
  if (!dateStr.includes('+') && !dateStr.endsWith('Z')) {
    d = new Date(d.getTime() - d.getTimezoneOffset() * 60_000)
  }
  return d.toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
}

export default function ConfigBackupPanel({ deviceId }: { deviceId: string }) {
  const [backups, setBackups] = useState<ConfigBackup[]>([])
  const [loading, setLoading] = useState(false)
  const [backing, setBacking] = useState(false)
  const [preview, setPreview] = useState<string | null>(null)
  const [selected, setSelected] = useState<ConfigBackup | null>(null)
  const [diff, setDiff] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const data = await fetchConfigBackups(deviceId)
      setBackups(data)
      if (data.length > 0 && !selected) setSelected(data[0])
    } catch (e: any) {
      setError(e.response?.data?.detail || e.message)
    } finally {
      setLoading(false)
    }
  }, [deviceId, selected])

  useEffect(() => { load() }, [load])

  async function handleBackup() {
    setBacking(true)
    setError(null)
    try {
      await createConfigBackup(deviceId)
      await load()
    } catch (e: any) {
      setError(e.response?.data?.detail || e.message)
    } finally {
      setBacking(false)
    }
  }

  async function handlePreview() {
    setError(null)
    try {
      const data = await previewCurrentConfig(deviceId)
      setPreview(data.content)
      setDiff(null)
    } catch (e: any) {
      setError(e.response?.data?.detail || e.message)
    }
  }

  async function viewContent(b: ConfigBackup) {
    setError(null)
    try {
      const data = await fetchConfigBackupContent(deviceId, b.id)
      setPreview(data.content)
      setDiff(null)
      setSelected(b)
    } catch (e: any) {
      setError(e.response?.data?.detail || e.message)
    }
  }

  async function viewDiff(b: ConfigBackup) {
    setError(null)
    try {
      const data = await fetchConfigDiff(deviceId, b.id)
      setDiff(data.diff)
      setPreview(null)
      setSelected(b)
    } catch (e: any) {
      setError(e.response?.data?.detail || e.message)
    }
  }

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <h2 style={{ fontSize: 18, margin: 0 }}>配置备份</h2>
        <div style={{ display: 'flex', gap: 8 }}>
          <button className="btn btn-sm" onClick={handlePreview} disabled={backing}>预览当前配置</button>
          <button className="btn btn-sm btn-primary" onClick={handleBackup} disabled={backing}>
            {backing ? '备份中...' : '立即备份'}
          </button>
        </div>
      </div>

      {error && <div className="alert alert-danger" style={{ marginBottom: 16, padding: 12, borderRadius: 6, background: 'rgba(248,81,73,0.1)', color: 'var(--accent-red)', border: '1px solid var(--accent-red)' }}>{error}</div>}

      <div className="grid-2">
        <div className="card">
          <h3 style={{ fontSize: 15, marginBottom: 12 }}>历史版本</h3>
          {loading ? <p style={{ color: 'var(--text-secondary)' }}>加载中...</p> : backups.length === 0 ? (
            <p style={{ color: 'var(--text-secondary)' }}>暂无备份记录。</p>
          ) : (
            <div className="table-wrapper">
              <table>
                <thead>
                  <tr><th>版本</th><th>时间</th><th>变更</th><th>操作</th></tr>
                </thead>
                <tbody>
                  {backups.map(b => (
                    <tr key={b.id} style={{ background: selected?.id === b.id ? 'rgba(88,166,255,0.08)' : undefined }}>
                      <td>rev{b.revision}</td>
                      <td>{fmtTimeCN(b.captured_at)}</td>
                      <td style={{ color: 'var(--text-secondary)', fontSize: 12 }}>{b.change_summary || '首次备份'}</td>
                      <td style={{ display: 'flex', gap: 6 }}>
                        <button className="btn btn-sm" onClick={() => viewContent(b)}>查看</button>
                        <button className="btn btn-sm" onClick={() => viewDiff(b)}>Diff</button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>

        <div className="card">
          <h3 style={{ fontSize: 15, marginBottom: 12 }}>
            {diff ? 'Diff 对比' : preview != null ? '配置内容' : '请选择操作'}
          </h3>
          {preview != null && (
            <pre style={{
              background: 'var(--bg-secondary)', border: '1px solid var(--border-color)',
              borderRadius: 6, padding: 12, height: 420, overflow: 'auto', fontSize: 12,
              color: 'var(--text-primary)', whiteSpace: 'pre-wrap', wordBreak: 'break-all',
            }}>{preview}</pre>
          )}
          {diff != null && (
            <pre style={{
              background: 'var(--bg-secondary)', border: '1px solid var(--border-color)',
              borderRadius: 6, padding: 12, height: 420, overflow: 'auto', fontSize: 12,
              color: 'var(--text-primary)', whiteSpace: 'pre-wrap', wordBreak: 'break-all',
            }}>{diff || '无差异'}</pre>
          )}
          {preview == null && diff == null && (
            <p style={{ color: 'var(--text-secondary)' }}>点击左侧「查看」或「Diff」在此展示。</p>
          )}
        </div>
      </div>
    </div>
  )
}
