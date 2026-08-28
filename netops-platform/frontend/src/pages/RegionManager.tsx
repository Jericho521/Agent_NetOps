import { useEffect, useState } from 'react'
import {
  listRegions, createRegion, updateRegion, deleteRegion,
  createSubRegion, updateSubRegion, deleteSubRegion,
  type RegionItem, type SubRegionItem
} from '../api'

export default function RegionManager() {
  const [regions, setRegions] = useState<RegionItem[]>([])
  const [loading, setLoading] = useState(false)

  // 新建区域表单
  const [showNewRegion, setShowNewRegion] = useState(false)
  const [newName, setNewName] = useState('')
  const [newDesc, setNewDesc] = useState('')

  // 新建子区域（按区域 ID）
  const [newSubByRegion, setNewSubByRegion] = useState<string | null>(null)
  const [newSubName, setNewSubName] = useState('')
  const [newSubDesc, setNewSubDesc] = useState('')

  // 编辑区域
  const [editingId, setEditingId] = useState<string | null>(null)
  const [editName, setEditName] = useState('')
  const [editDesc, setEditDesc] = useState('')

  // 编辑子区域
  const [editingSubId, setEditingSubId] = useState<string | null>(null)
  const [editSubName, setEditSubName] = useState('')
  const [editSubDesc, setEditSubDesc] = useState('')

  useEffect(() => { load() }, [])

  async function load() {
    setLoading(true)
    try {
      const data = await listRegions()
      setRegions(data)
    } catch (e) {
      console.error(e)
    } finally {
      setLoading(false)
    }
  }

  async function handleCreateRegion() {
    if (!newName.trim()) return
    try {
      await createRegion({ name: newName.trim(), description: newDesc.trim() || undefined })
      setShowNewRegion(false); setNewName(''); setNewDesc('')
      await load()
    } catch (e) { alert('创建失败') }
  }

  async function handleUpdateRegion(id: string) {
    if (!editName.trim()) return
    try {
      await updateRegion(id, { name: editName.trim(), description: editDesc.trim() || undefined })
      setEditingId(null)
      await load()
    } catch (e) { alert('更新失败') }
  }

  async function handleDeleteRegion(id: string) {
    if (!confirm('删除区域会级联删除其下所有子区域，确定？')) return
    try {
      await deleteRegion(id)
      await load()
    } catch (e) { alert('删除失败') }
  }

  async function handleCreateSub(regionId: string) {
    if (!newSubName.trim()) return
    try {
      await createSubRegion(regionId, { name: newSubName.trim(), description: newSubDesc.trim() || undefined })
      setNewSubByRegion(null); setNewSubName(''); setNewSubDesc('')
      await load()
    } catch (e) { alert('创建失败') }
  }

  async function handleUpdateSub(id: string) {
    if (!editSubName.trim()) return
    try {
      await updateSubRegion(id, { name: editSubName.trim(), description: editSubDesc.trim() || undefined })
      setEditingSubId(null)
      await load()
    } catch (e) { alert('更新失败') }
  }

  async function handleDeleteSub(id: string) {
    if (!confirm('确定删除该子区域？')) return
    try {
      await deleteSubRegion(id)
      await load()
    } catch (e) { alert('删除失败') }
  }

  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 20 }}>
        <h2 style={{ margin: 0 }}>区域管理</h2>
        {!showNewRegion ? (
          <button className="btn btn-primary" onClick={() => setShowNewRegion(true)}>+ 新增区域</button>
        ) : (
          <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
            <input value={newName} onChange={e => setNewName(e.target.value)} placeholder="区域名称"
                   onKeyDown={e => e.key === 'Enter' && handleCreateRegion()}
                   style={{ background: 'var(--bg-secondary)', border: '1px solid var(--border-color)', borderRadius: 6, color: 'var(--text-primary)', padding: '4px 10px' }} />
            <input value={newDesc} onChange={e => setNewDesc(e.target.value)} placeholder="描述（可选）"
                   onKeyDown={e => e.key === 'Enter' && handleCreateRegion()}
                   style={{ background: 'var(--bg-secondary)', border: '1px solid var(--border-color)', borderRadius: 6, color: 'var(--text-primary)', padding: '4px 10px', width: 200 }} />
            <button className="btn btn-sm" onClick={handleCreateRegion}>保存</button>
            <button className="btn btn-sm" onClick={() => setShowNewRegion(false)}>取消</button>
          </div>
        )}
      </div>

      {loading && regions.length === 0 ? (
        <p style={{ color: 'var(--text-secondary)' }}>加载中…</p>
      ) : regions.length === 0 ? (
        <div className="card" style={{ padding: 24, textAlign: 'center' }}>
          <p style={{ color: 'var(--text-secondary)' }}>暂无区域，点击右上角新增。</p>
        </div>
      ) : (
        <div className="card" style={{ padding: 16 }}>
          {regions.map(r => (
            <div key={r.id} style={{
              border: '1px solid var(--border-color)',
              borderRadius: 8,
              padding: 16,
              marginBottom: 12,
              background: 'var(--bg-secondary)',
            }}>
              {/* 区域头部 */}
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                <div style={{ flex: 1 }}>
                  {editingId === r.id ? (
                    <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
                      <input value={editName} onChange={e => setEditName(e.target.value)}
                             onKeyDown={e => e.key === 'Enter' && handleUpdateRegion(r.id)}
                             style={{ background: 'var(--bg-primary)', border: '1px solid #58a6ff', borderRadius: 4, color: 'var(--text-primary)', padding: '3px 8px', fontSize: 14, fontWeight: 600 }} />
                      <input value={editDesc} onChange={e => setEditDesc(e.target.value)} placeholder="描述"
                             onKeyDown={e => e.key === 'Enter' && handleUpdateRegion(r.id)}
                             style={{ background: 'var(--bg-primary)', border: '1px solid #58a6ff', borderRadius: 4, color: 'var(--text-primary)', padding: '3px 8px', width: 200 }} />
                      <button className="btn btn-sm" onClick={() => handleUpdateRegion(r.id)}>保存</button>
                      <button className="btn btn-sm" onClick={() => setEditingId(null)}>取消</button>
                    </div>
                  ) : (
                    <>
                      <span style={{ fontSize: 15, fontWeight: 600 }}>{r.name}</span>
                      {r.description && <span style={{ marginLeft: 8, color: 'var(--text-secondary)', fontSize: 13 }}>— {r.description}</span>}
                    </>
                  )}
                </div>
                <div style={{ display: 'flex', gap: 6, marginLeft: 16 }}>
                  {editingId !== r.id && (
                    <>
                      <button className="btn btn-sm" onClick={() => { setEditingId(r.id); setEditName(r.name); setEditDesc(r.description || '') }}>编辑</button>
                      <button className="btn btn-sm btn-danger" onClick={() => handleDeleteRegion(r.id)}>删除</button>
                    </>
                  )}
                </div>
              </div>

              {/* 子区域列表 */}
              <div style={{ marginTop: 12, paddingLeft: 20 }}>
                {(r.sub_regions || []).length > 0 && (
                  <div style={{ display: 'flex', gap: 24, flexWrap: 'wrap' }}>
                    {(r.sub_regions || []).map(sr => (
                      <div key={sr.id} style={{
                        background: 'var(--bg-primary)',
                        border: '1px solid var(--border-color)',
                        borderRadius: 6,
                        padding: '8px 12px',
                        minWidth: 180,
                        display: 'inline-flex',
                        justifyContent: 'space-between',
                        alignItems: 'center',
                        gap: 8,
                      }}>
                        {editingSubId === sr.id ? (
                          <>
                            <input value={editSubName} onChange={e => setEditSubName(e.target.value)}
                                   onKeyDown={e => e.key === 'Enter' && handleUpdateSub(sr.id)}
                                   style={{ background: 'var(--bg-secondary)', border: '1px solid #58a6ff', borderRadius: 4, color: 'var(--text-primary)', padding: '2px 6px', fontSize: 13 }} />
                            <input value={editSubDesc} onChange={e => setEditSubDesc(e.target.value)} placeholder="描述"
                                   onKeyDown={e => e.key === 'Enter' && handleUpdateSub(sr.id)}
                                   style={{ background: 'var(--bg-secondary)', border: '1px solid #58a6ff', borderRadius: 4, color: 'var(--text-primary)', padding: '2px 6px', width: 120, fontSize: 13 }} />
                            <button className="btn btn-sm" onClick={() => handleUpdateSub(sr.id)} style={{ padding: '1px 6px', fontSize: 11 }}>✓</button>
                            <button className="btn btn-sm" onClick={() => setEditingSubId(null)} style={{ padding: '1px 6px', fontSize: 11 }}>✕</button>
                          </>
                        ) : (
                          <>
                            <span style={{ fontSize: 13 }}>{sr.name}</span>
                            {sr.description && <span style={{ fontSize: 11, color: 'var(--text-secondary)' }}>({sr.description})</span>}
                            <div style={{ display: 'flex', gap: 4 }}>
                              <button className="btn btn-sm" onClick={() => { setEditingSubId(sr.id); setEditSubName(sr.name); setEditSubDesc(sr.description || '') }}
                                      style={{ padding: '1px 5px', fontSize: 11 }}>编辑</button>
                              <button className="btn btn-sm btn-danger" onClick={() => handleDeleteSub(sr.id)}
                                      style={{ padding: '1px 5px', fontSize: 11 }}>删</button>
                            </div>
                          </>
                        )}
                      </div>
                    ))}
                  </div>
                )}

                {/* 新增子区域 */}
                {newSubByRegion === r.id ? (
                  <div style={{ marginTop: 8, display: 'flex', gap: 6, alignItems: 'center' }}>
                    <input value={newSubName} onChange={e => setNewSubName(e.target.value)} placeholder="子区域名称"
                           onKeyDown={e => e.key === 'Enter' && handleCreateSub(r.id)}
                           style={{ background: 'var(--bg-primary)', border: '1px solid #58a6ff', borderRadius: 4, color: 'var(--text-primary)', padding: '3px 8px', fontSize: 13 }} />
                    <input value={newSubDesc} onChange={e => setNewSubDesc(e.target.value)} placeholder="描述（可选）"
                           onKeyDown={e => e.key === 'Enter' && handleCreateSub(r.id)}
                           style={{ background: 'var(--bg-primary)', border: '1px solid #58a6ff', borderRadius: 4, color: 'var(--text-primary)', padding: '3px 8px', width: 150, fontSize: 13 }} />
                    <button className="btn btn-sm" onClick={() => handleCreateSub(r.id)}>保存</button>
                    <button className="btn btn-sm" onClick={() => setNewSubByRegion(null)}>取消</button>
                  </div>
                ) : (
                  <button className="btn btn-sm" style={{ marginTop: 8, opacity: 0.7 }}
                          onClick={() => setNewSubByRegion(r.id)}>
                    + 新增子区域
                  </button>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
