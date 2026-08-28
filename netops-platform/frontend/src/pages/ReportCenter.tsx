import { useEffect, useState } from 'react'
import { generateReport, listReportInstances, deleteReport, downloadReportUrl, type ReportInstance } from '../api'

export default function ReportCenter() {
  const [instances, setInstances] = useState<ReportInstance[]>([])
  const [loading, setLoading] = useState(false)
  const [generating, setGenerating] = useState(false)

  useEffect(() => {
    load()
  }, [])

  async function load() {
    setLoading(true)
    try {
      const data = await listReportInstances()
      setInstances(data)
    } catch (e) {
      console.error(e)
    } finally {
      setLoading(false)
    }
  }

  async function handleGenerate() {
    setGenerating(true)
    try {
      await generateReport('daily', 24)
      await load()
    } catch (e) {
      console.error(e)
      alert('生成失败')
    } finally {
      setGenerating(false)
    }
  }

  async function handleDelete(id: string) {
    if (!confirm('确定删除该报表？')) return
    try {
      await deleteReport(id)
      await load()
    } catch (e) {
      console.error(e)
    }
  }

  function formatTime(iso: string) {
    const d = new Date(iso)
    return isNaN(d.getTime()) ? iso : d.toLocaleString()
  }

  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 20 }}>
        <h2 style={{ margin: 0 }}>报表中心</h2>
        <button className="btn btn-primary" onClick={handleGenerate} disabled={generating}>
          {generating ? '生成中...' : '生成日报'}
        </button>
      </div>

      <div className="card" style={{ padding: 16 }}>
        {loading ? (
          <p style={{ color: 'var(--text-secondary)' }}>加载中…</p>
        ) : instances.length === 0 ? (
          <p style={{ color: 'var(--text-secondary)' }}>暂无报表，点击右上角生成日报。</p>
        ) : (
          <table className="table">
            <thead>
              <tr>
                <th>类型</th>
                <th>生成时间</th>
                <th>状态</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              {instances.map(inst => (
                <tr key={inst.id}>
                  <td>{inst.report_type === 'daily' ? '日报' : inst.report_type === 'weekly' ? '周报' : '月报'}</td>
                  <td>{formatTime(inst.created_at)}</td>
                  <td>
                    <span className={`badge ${inst.status === 'completed' ? 'badge-success' : 'badge-danger'}`}>
                      {inst.status === 'completed' ? '完成' : '失败'}
                    </span>
                    {inst.error_message && (
                      <span style={{ marginLeft: 8, color: 'var(--text-danger)' }}>{inst.error_message}</span>
                    )}
                  </td>
                  <td>
                    <div style={{ display: 'flex', gap: 8 }}>
                      {inst.pdf_path && (
                        <a className="btn btn-sm" href={downloadReportUrl(inst.id, 'pdf')} target="_blank" rel="noreferrer">下载 PDF</a>
                      )}
                      {inst.excel_path && (
                        <a className="btn btn-sm" href={downloadReportUrl(inst.id, 'excel')} target="_blank" rel="noreferrer">下载 Excel</a>
                      )}
                      <button className="btn btn-sm btn-danger" onClick={() => handleDelete(inst.id)}>删除</button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}
