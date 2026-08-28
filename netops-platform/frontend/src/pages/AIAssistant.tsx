import { useState, useEffect, useRef } from 'react'
import { chatWithAI, getAIContext, AIContextStats } from '../api'

interface Message {
  role: 'user' | 'assistant'
  content: string
}

export default function AIAssistant() {
  const [messages, setMessages] = useState<Message[]>([
    { role: 'assistant', content: '欢迎使用 NetOps AI 运维助手。我可以基于当前平台数据，回答设备状态、告警分析、容量评估及配置建议等问题。' },
  ])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [stats, setStats] = useState<AIContextStats | null>(null)
  const scrollRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    loadStats()
  }, [])

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight
    }
  }, [messages])

  async function loadStats() {
    try {
      const data = await getAIContext()
      setStats(data)
    } catch (e) {
      console.error('加载平台数据失败', e)
    }
  }

  function buildSystemPrompt(): string {
    if (!stats) {
      return '你是 NetOps 网络运维监控平台的 AI 助手，请根据用户问题给出运维建议。'
    }
    return (
      '你是 NetOps 网络运维监控平台的 AI 助手。当前平台实时数据如下：\n' +
      `- 设备总数：${stats.devices_total}\n` +
      `- 在线设备：${stats.devices_online}\n` +
      `- 离线设备：${stats.devices_offline}\n` +
      `- 异常设备：${stats.devices_error}\n` +
      `- 未恢复告警：${stats.active_alerts}\n` +
      `- 近期告警：${stats.recent_alerts}\n\n` +
      '请基于以上数据回答用户问题。如果用户没有指定问题，请给出健康度评估和处置建议。'
    )
  }

  async function handleSend() {
    const text = input.trim()
    if (!text || loading) return
    setInput('')
    const userMsg: Message = { role: 'user', content: text }
    setMessages(prev => [...prev, userMsg])
    setLoading(true)

    try {
      const payload = [
        { role: 'system', content: buildSystemPrompt() },
        ...messages.filter(m => m.role !== 'assistant' || !m.content.startsWith('欢迎使用 NetOps AI 运维助手')),
        { role: 'user', content: text },
      ]
      const { content } = await chatWithAI(payload)
      setMessages(prev => [...prev, { role: 'assistant', content: content || '（无返回）' }])
    } catch (e: any) {
      setMessages(prev => [...prev, { role: 'assistant', content: `调用失败：${e.response?.data?.detail || e.message}` }])
    } finally {
      setLoading(false)
    }
  }

  async function handleQuickPrompt(prompt: string, label: string) {
    if (loading) return
    if (label === '知识库') {
      setMessages(prev => [...prev, { role: 'user', content: prompt }, { role: 'assistant', content: '知识库功能正在建设中，敬请期待。' }])
      return
    }
    setMessages(prev => [...prev, { role: 'user', content: prompt }])
    setLoading(true)
    try {
      const payload = [
        { role: 'system', content: buildSystemPrompt() },
        ...messages.filter(m => m.role !== 'assistant' || !m.content.startsWith('欢迎使用 NetOps AI 运维助手')),
        { role: 'user', content: prompt },
      ]
      const { content } = await chatWithAI(payload)
      setMessages(prev => [...prev, { role: 'assistant', content: content || '（无返回）' }])
    } catch (e: any) {
      setMessages(prev => [...prev, { role: 'assistant', content: `调用失败：${e.response?.data?.detail || e.message}` }])
    } finally {
      setLoading(false)
    }
  }

  function handleKeyDown(e: React.KeyboardEvent) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  const quickButtons = [
    { label: '巡检报告', prompt: '请基于当前平台数据，生成一份网络关键节点巡检报告。报告应包含：1）设备整体运行状态（在线/离线/异常数量）；2）各设备的 CPU/内存使用率概况；3）关键接口带宽利用率与流量情况；4）当前告警与处置建议；5）巡检结论与后续优化建议。格式清晰，便于导出。' },
    { label: '日报周报', prompt: '请基于当前平台数据，生成一份网络运维日报/周报摘要，包含设备运行状态、告警处理情况、容量使用趋势及今日/本周重点工作建议。' },
    { label: '半年度汇报', prompt: '请基于当前平台数据，生成一份半年度网络运维工作汇报框架，包含设备运行概况、告警统计与分析、容量规划建议、下半年工作方向。' },
    { label: '告警分析', prompt: '请分析当前平台告警，给出根因分析、影响范围评估和具体处置建议，并按优先级排序。' },
    { label: '知识库', prompt: '知识库' },
  ]

  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column', gap: 16 }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <h2 style={{ margin: 0 }}>AI 运维助手</h2>
      </div>

      {/* 聊天区 */}
      <div style={{
        flex: 1,
        display: 'flex',
        flexDirection: 'column',
        border: '1px solid var(--border-color)',
        borderRadius: 12,
        overflow: 'hidden',
        background: 'var(--bg-secondary)',
        minHeight: 400,
      }}>
        <div ref={scrollRef} style={{
          flex: 1,
          overflowY: 'auto',
          padding: 16,
          display: 'flex',
          flexDirection: 'column',
          gap: 12,
        }}>
          {messages.map((m, i) => (
            <div key={i} style={{
              alignSelf: m.role === 'user' ? 'flex-end' : 'flex-start',
              maxWidth: '80%',
              padding: '10px 14px',
              borderRadius: 10,
              background: m.role === 'user' ? 'var(--accent-blue)' : 'var(--bg-primary)',
              color: m.role === 'user' ? '#fff' : 'var(--text-primary)',
              fontSize: 14,
              lineHeight: 1.6,
              whiteSpace: 'pre-wrap',
              wordBreak: 'break-word',
            }}>
              {m.content}
            </div>
          ))}
          {loading && (
            <div style={{ alignSelf: 'flex-start', padding: '8px 12px', fontSize: 13, color: 'var(--text-secondary)' }}>
              思考中…
            </div>
          )}
        </div>

        {/* 快捷按钮 */}
        <div style={{
          padding: '12px 16px',
          borderTop: '1px solid var(--border-color)',
          display: 'flex',
          flexWrap: 'wrap',
          gap: 10,
          alignItems: 'center',
        }}>
          <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>快捷指令：</span>
          {quickButtons.map(btn => (
            <button
              key={btn.label}
              onClick={() => handleQuickPrompt(btn.prompt, btn.label)}
              disabled={loading}
              style={{
                padding: '6px 14px',
                borderRadius: 999,
                border: '1px solid var(--border-color)',
                background: 'var(--bg-primary)',
                color: 'var(--text-primary)',
                fontSize: 13,
                cursor: loading ? 'not-allowed' : 'pointer',
                opacity: loading ? 0.6 : 1,
                transition: 'all 0.2s',
              }}
              onMouseEnter={e => {
                if (!loading) {
                  e.currentTarget.style.borderColor = 'var(--accent-blue)'
                  e.currentTarget.style.color = 'var(--accent-blue)'
                }
              }}
              onMouseLeave={e => {
                e.currentTarget.style.borderColor = 'var(--border-color)'
                e.currentTarget.style.color = 'var(--text-primary)'
              }}
            >
              {btn.label}
            </button>
          ))}
        </div>

        <div style={{ padding: 12, borderTop: '1px solid var(--border-color)', display: 'flex', gap: 8 }}>
          <textarea
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="请输入您的问题，例如当前网络健康状况、在线设备数量等。"
            rows={1}
            style={{
              flex: 1,
              resize: 'none',
              border: '1px solid var(--border-color)',
              borderRadius: 8,
              padding: '10px 12px',
              background: 'var(--bg-primary)',
              color: 'var(--text-primary)',
              fontSize: 14,
              outline: 'none',
              minHeight: 40,
              maxHeight: 120,
            }}
          />
          <button className="btn btn-primary" onClick={handleSend} disabled={loading || !input.trim()}>发送</button>
        </div>
      </div>
    </div>
  )
}

