import { useState, useRef, useEffect, useCallback } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import KnowledgeManager from './components/KnowledgeManager'

const API_BASE = 'http://localhost:8000'
const WS_URL = 'ws://localhost:8000/api/ws/chat'

class WSManager {
  constructor() {
    this.ws = null
    this.callbacks = new Map()
    this.connecting = false
    this.heartbeatTimer = null
    this.processedIds = new Set()
  }

  connect() {
    if (this.ws?.readyState === WebSocket.OPEN) return
    if (this.connecting) return
    this.connecting = true

    this.ws = new WebSocket(WS_URL)

    this.ws.onopen = () => {
      this.connecting = false
      this.notify({ type: 'open' })
      this.heartbeatTimer = setInterval(() => {
        if (this.ws?.readyState === WebSocket.OPEN) this.send({ type: 'heartbeat' })
      }, 30000)
    }

    this.ws.onmessage = (e) => {
      try {
        const data = JSON.parse(e.data)
        if (data.type === 'heartbeat_ack') return
        this.notify({ type: 'message', data })
      } catch { /* ignore parse errors */ }
    }

    this.ws.onclose = () => {
      this.connecting = false
      clearInterval(this.heartbeatTimer)
      this.notify({ type: 'close' })
      setTimeout(() => this.connect(), 5000)
    }

    this.ws.onerror = () => { this.connecting = false }
  }

  send(msg) {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(msg))
    }
  }

  subscribe(key, fn) {
    this.callbacks.set(key, fn)
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) this.connect()
    return () => this.callbacks.delete(key)
  }

  notify(event) {
    this.callbacks.forEach(fn => {
      try {
        fn(event)
      } catch (e) {
        console.error('[WSManager] 回调执行异常:', e)
      }
    })
  }
}

const wsManager = new WSManager()

const chatStates = new Map()

function getState(cid) {
  if (!cid) return null
  if (!chatStates.has(cid)) {
    chatStates.set(cid, {
      messages: [],
      loading: false,
      progress: '',
      uploaded: null,
      streaming: false,
    })
  }
  return chatStates.get(cid)
}

function updateState(cid, patch) {
  const s = getState(cid)
  if (s) {
    const newState = { ...s, ...patch }
    chatStates.set(cid, newState)
    return newState
  }
  return s
}

function MemoMarkdown({ text }) {
  return ReactMarkdown({
    children: text,
    remarkPlugins: [remarkGfm],
    components: {
      table: ({ children }) => <div className="overflow-x-auto my-2"><table>{children}</table></div>,
      a: ({ href, children }) => <a href={href} target="_blank" rel="noopener noreferrer" className="text-blue-500 hover:underline">{children}</a>,
    },
  })
}
const Markdown = ReactMarkdown.memo ? ReactMarkdown.memo(MemoMarkdown) : MemoMarkdown

// 若 text 是形如 {"text": "..."} 的 JSON，提取出内部的 text 字段；否则原样返回
function extractTextIfJson(text) {
  if (typeof text !== 'string') return text
  const trimmed = text.trim()
  if (!trimmed.startsWith('{') || !trimmed.endsWith('}')) return text
  try {
    const parsed = JSON.parse(trimmed)
    if (parsed && typeof parsed === 'object' && typeof parsed.text === 'string') {
      return parsed.text
    }
  } catch (_) { /* 非合法 JSON 或不含 text 字段，忽略 */ }
  return text
}

function isReport(text) {
  if (!text) return false
  const candidate = extractTextIfJson(text)
  // 问诊完成消息也按报告样式渲染
  if (candidate.startsWith('【问诊完成】')) return true
  return candidate.includes('###') && (candidate.includes('健康评估') || candidate.includes('诊断') || candidate.includes('风险'))
}

function hasMarkdown(text) {
  if (!text) return false
  const candidate = extractTextIfJson(text)
  return /[#*`>\[\]|]/.test(candidate) || candidate.includes('\n- ') || candidate.includes('\n1. ')
}

export default function App() {
  const [view, setView] = useState('chat')
  const [detailId, setDetailId] = useState(null)
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [convs, setConvs] = useState([])
  const [activeCid, setActiveCid] = useState(() => {
    try { return localStorage.getItem('ha_active_cid') } catch { return null }
  })
  const [connected, setConnected] = useState(false)
  const [dark, setDark] = useState(() => {
    try { return localStorage.getItem('ha_dark') === '1' } catch { return true }
  })
  const [searchQuery, setSearchQuery] = useState('')

  useEffect(() => {
    if (activeCid) localStorage.setItem('ha_active_cid', activeCid)
  }, [activeCid])

  useEffect(() => {
    localStorage.setItem('ha_dark', dark ? '1' : '0')
    document.documentElement.classList.toggle('dark', dark)
  }, [dark])

  useEffect(() => {
    return wsManager.subscribe('app_conn', (e) => {
      if (e.type === 'open') setConnected(true)
      else if (e.type === 'close') setConnected(false)
    })
  }, [])

  const loadConvs = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/api/history?page=1&page_size=50`)
      const data = await res.json()
      const list = data.data || []
      setConvs(list)
      if (!activeCid && list.length > 0) setActiveCid(list[0].id)
    } catch { /* ignore */ }
  }, [activeCid])

  useEffect(() => { loadConvs() }, [])

  const newConv = async () => {
    const title = prompt('请输入对话标题：') || '新对话'
    try {
      const res = await fetch(`${API_BASE}/api/history/create`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title })
      })
      const data = await res.json()
      if (data.data?.id) {
        const cid = data.data.id
        chatStates.set(cid, {
          messages: [],
          loading: false,
          progress: '',
          uploaded: null,
          streaming: false,
        })
        setActiveCid(cid)
        setView('chat')
        setSidebarOpen(false)
        loadConvs()
      }
    } catch (e) { console.error('创建失败', e) }
  }

  const renameConv = async (cid, e) => {
    e.stopPropagation()
    const currentConv = convs.find(c => c.id === cid)
    if (!currentConv) return
    const newTitle = prompt('请输入新标题：', currentConv.title)
    if (newTitle === null) return
    if (!newTitle.trim()) {
      alert('标题不能为空')
      return
    }
    try {
      await fetch(`${API_BASE}/api/history/${cid}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title: newTitle.trim() })
      })
      loadConvs()
    } catch (e) { console.error('重命名失败', e) }
  }

  const viewConv = (cid) => {
    setActiveCid(cid)
    setView('chat')
    setSidebarOpen(false)
  }

  const deleteConv = async (cid, e) => {
    e.stopPropagation()
    if (!confirm('确定删除此对话？')) return
    try {
      await fetch(`${API_BASE}/api/history/${cid}`, { method: 'DELETE' })
      chatStates.delete(cid)
      if (activeCid === cid) setActiveCid(null)
      loadConvs()
    } catch { /* ignore */ }
  }

  const filteredConvs = convs.filter(c =>
    !searchQuery || c.title?.toLowerCase().includes(searchQuery.toLowerCase())
  )

  return (
    <div className={`flex h-screen ${dark ? 'dark' : ''}`}>
      <div className="flex h-screen w-full bg-white dark:bg-[#16163a] text-gray-900 dark:text-gray-100 transition-colors">
        <aside className={`bg-gray-50 dark:bg-[#1a1a2e] border-r border-gray-200 dark:border-[#2a2a5a] w-72 flex flex-col shrink-0
          ${sidebarOpen ? 'translate-x-0' : '-translate-x-full'} md:translate-x-0
          transition-transform duration-300 absolute md:relative z-30 h-full`}>

          <div className="p-4 border-b border-gray-200 dark:border-[#2a2a5a]">
            <h1 className="text-lg font-bold text-blue-600 dark:text-blue-400 flex items-center gap-2">
              <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4.318 6.318a4.5 4.5 0 000 6.364L12 20.364l7.682-7.682a4.5 4.5 0 00-6.364-6.364L12 7.636l-1.318-1.318a4.5 4.5 0 00-6.364 0z" />
              </svg>
              智能健康助手
            </h1>
          </div>

          <button onClick={newConv}
            className="mx-3 my-3 p-2.5 border-2 border-dashed border-gray-300 dark:border-gray-600 rounded-xl
              text-gray-500 dark:text-gray-400 hover:border-blue-400 hover:text-blue-500
              dark:hover:border-blue-500 dark:hover:text-blue-400 transition-all
              flex items-center justify-center gap-2 text-sm">
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
            </svg>
            新对话
          </button>

          <button
            onClick={() => { setView('knowledge'); setSidebarOpen(false) }}
            className="w-full px-3 py-2 rounded-lg bg-gray-100 dark:bg-[#252550] hover:bg-gray-200 dark:hover:bg-[#2a2a5a] flex items-center justify-center gap-2 text-sm">
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253" />
            </svg>
            知识库
          </button>

          <div className="px-3 mb-2">
            <input
              type="text" value={searchQuery} onChange={e => setSearchQuery(e.target.value)}
              placeholder="搜索对话..."
              className="w-full px-3 py-1.5 text-sm rounded-lg border border-gray-200 dark:border-[#2a2a5a]
                bg-white dark:bg-[#252550] outline-none focus:ring-2 focus:ring-blue-500
                placeholder-gray-400 dark:placeholder-gray-500"
            />
          </div>

          <div className="flex-1 overflow-y-auto px-2">
            <h2 className="px-3 py-2 text-xs font-semibold text-gray-400 dark:text-gray-500 uppercase tracking-wider">历史记录</h2>
            {filteredConvs.length === 0 && (
              <p className="px-3 py-4 text-sm text-gray-400 dark:text-gray-500 text-center">暂无对话记录</p>
            )}
            {filteredConvs.map(c => (
              <div key={c.id}
                onClick={() => viewConv(c.id)}
                onDoubleClick={(e) => renameConv(c.id, e)}
                className={`group w-full px-3 py-2.5 rounded-lg cursor-pointer flex items-center justify-between
                  ${activeCid === c.id ? 'bg-blue-50 dark:bg-blue-900/30' : 'hover:bg-gray-100 dark:hover:bg-[#252550]'}`}
                title="双击修改标题">
                <div className="min-w-0 flex-1">
                  <div className={`text-sm truncate ${activeCid === c.id ? 'text-blue-700 dark:text-blue-300 font-medium' : 'text-gray-700 dark:text-gray-300'}`}>
                    {c.title || '新对话'}
                  </div>
                  <div className="text-xs text-gray-400 dark:text-gray-500 mt-0.5">
                    {new Date(c.created_at).toLocaleDateString('zh-CN')}
                  </div>
                </div>
                <button onClick={(e) => deleteConv(c.id, e)}
                  className="opacity-0 group-hover:opacity-100 p-1 hover:bg-red-100 dark:hover:bg-red-900/30 rounded transition-all">
                  <svg className="w-4 h-4 text-gray-400 hover:text-red-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                  </svg>
                </button>
              </div>
            ))}
          </div>

          <div className="p-3 border-t border-gray-200 dark:border-[#2a2a5a] flex items-center justify-between">
            <span className="text-xs text-gray-400 dark:text-gray-500">{connected ? '已连接' : '连接中...'}</span>
            <button onClick={() => setDark(!dark)}
              className="p-2 rounded-lg hover:bg-gray-200 dark:hover:bg-[#252550] transition-colors"
              title={dark ? '切换浅色模式' : '切换深色模式'}>
              {dark ? (
                <svg className="w-5 h-5 text-yellow-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 3v1m0 16v1m9-9h-1M4 12H3m15.364 6.364l-.707-.707M6.343 6.343l-.707-.707m12.728 0l-.707.707M6.343 17.657l-.707.707M16 12a4 4 0 11-8 0 4 4 0 018 0z" />
                </svg>
              ) : (
                <svg className="w-5 h-5 text-gray-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M20.354 15.354A9 9 0 018.646 3.646 9.003 9.003 0 0012 21a9.003 9.003 0 008.354-5.646z" />
                </svg>
              )}
            </button>
          </div>
        </aside>

        {sidebarOpen && <div className="fixed inset-0 bg-black/50 z-20 md:hidden" onClick={() => setSidebarOpen(false)} />}

        <main className="flex-1 flex flex-col min-w-0">
          <header className="bg-white dark:bg-[#1a1a2e] border-b border-gray-200 dark:border-[#2a2a5a] px-4 py-3 flex items-center justify-between">
            <button onClick={() => setSidebarOpen(!sidebarOpen)} className="md:hidden p-2 hover:bg-gray-100 dark:hover:bg-[#252550] rounded-lg">
              <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
              </svg>
            </button>
            <div className="flex items-center gap-3">
              <div className={`w-2 h-2 rounded-full ${connected ? 'bg-green-500' : 'bg-red-500'}`} />
              <span className="text-sm text-gray-500 dark:text-gray-400">{connected ? '服务就绪' : '连接中...'}</span>
            </div>
          </header>

          {view === 'knowledge' ? (
            <KnowledgeManager dark={dark} />
          ) : view === 'detail' && detailId ? (
            <DetailPage reportId={detailId} onBack={() => setView('chat')} dark={dark} />
          ) : (
            <ChatView
              key={activeCid || 'new'}
              cid={activeCid}
              onRefresh={loadConvs}
              connected={connected}
              dark={dark}
            />
          )}
        </main>
      </div>
    </div>
  )
}

function ChatView({ cid, onRefresh, connected, dark }) {
  const [, forceUpdate] = useState(0)
  const rerender = useCallback(() => forceUpdate(v => v + 1), [])
  const [input, setInput] = useState('')
  const [showDownloadOptions, setShowDownloadOptions] = useState(false)
  const [mdPreview, setMdPreview] = useState(null)
  const [isRecording, setIsRecording] = useState(false)
  const [voiceEnabled, setVoiceEnabled] = useState(true)
  const [showThinking, setShowThinking] = useState(false)
  const msgsEndRef = useRef(null)
  const inputRef = useRef(null)
  const sendLockRef = useRef(false)
  const streamBufferRef = useRef('')
  const stuckTimerRef = useRef(null)
  const activeRequestIdsRef = useRef(new Set())
  const mediaRecorderRef = useRef(null)
  const audioChunksRef = useRef([])

  const [localState, setLocalState] = useState(() => 
    getState(cid) || { messages: [], loading: false, progress: '', uploaded: null, streaming: false }
  )

  const localUpdateState = useCallback((patch) => {
    const newState = updateState(cid, patch)
    if (newState) setLocalState(newState)
    return newState
  }, [cid])

  const clearStuckTimer = useCallback(() => {
    if (stuckTimerRef.current) {
      clearTimeout(stuckTimerRef.current)
      stuckTimerRef.current = null
    }
  }, [])

  const finishLoading = useCallback(() => {
    localUpdateState({ loading: false, progress: '', streaming: false })
    sendLockRef.current = false
    clearStuckTimer()
  }, [localUpdateState, clearStuckTimer])

  useEffect(() => {
    const s = getState(cid) || { messages: [], loading: false, progress: '', uploaded: null, streaming: false }
    setLocalState(s)
  }, [cid])

  useEffect(() => {
    sendLockRef.current = false
    streamBufferRef.current = ''
    activeRequestIdsRef.current.clear()
    if (stuckTimerRef.current) {
      clearTimeout(stuckTimerRef.current)
      stuckTimerRef.current = null
    }
    return () => {
      localUpdateState({ loading: false, progress: '', streaming: false })
      clearStuckTimer()
    }
  }, [cid, localUpdateState, clearStuckTimer])

  useEffect(() => {
    if (!cid) return
    if (localState.messages.length > 0) return

    ;(async () => {
      try {
        const res = await fetch(`${API_BASE}/api/history/${cid}`)
        const data = await res.json()
        if (data.data?.messages) {
          const msgs = data.data.messages
            .filter(m => {
              const c = String(m.content || '').trim()
              if (c === '[工具调用]') return false
              if (c.startsWith('[must_ask]') || c.startsWith('[suggest_ask]') || c.startsWith('[overview]') || c.startsWith('[tool_call]')) return false
              return true
            })
            .map(m => ({
              role: m.role,
              text: m.content,
              isReport: m.message_type === 'report',
              createdAt: m.created_at,
            }))

          if (data.data?.health_reports && data.data.health_reports.length > 0) {
            const reports = data.data.health_reports.map(r => ({
              role: 'assistant',
              text: r.content_markdown,
              isReport: true,
              createdAt: r.created_at,
            }))
            msgs.push(...reports)
            msgs.sort((a, b) => new Date(a.createdAt) - new Date(b.createdAt))
          }

          localUpdateState({ messages: msgs })
        }
      } catch {}
    })()
  }, [cid, localState.messages.length])

  useEffect(() => {
    if (!cid) return
    const key = `chat_${cid}`

    return wsManager.subscribe(key, (event) => {
      console.log('[WS] 收到消息:', event.data?.type, event.data)
      if (event.type !== 'message') return
      const { type, content, message, report, text, error, conversation_id: mCid, request_id } = event.data

      if (!mCid || mCid !== cid) return

      const currentState = getState(cid)
      if (!currentState) return

      const progressText = content || message || ''

      if (type === 'stream_end') {
        let newMessages = [...currentState.messages]
        const last = newMessages[newMessages.length - 1]
        if (last && last.streaming) {
          newMessages[newMessages.length - 1] = {
            ...last,
            streaming: false,
            text: streamBufferRef.current
          }
        }
        const replyText = streamBufferRef.current
        streamBufferRef.current = ''
        activeRequestIdsRef.current.delete(request_id)
        localUpdateState({ messages: newMessages, loading: false, progress: '', streaming: false })
        sendLockRef.current = false
        clearStuckTimer()
        if (replyText && voiceEnabled) {
          playTTS(replyText)
        }
        return
      }

      if (type === 'report' && report) {
        sendLockRef.current = false
        clearStuckTimer()
        activeRequestIdsRef.current.delete(request_id)
        const currentMessages = getState(cid)?.messages || localState.messages || []
        const filteredMessages = currentMessages.filter(m => !m.isReport)
        const newMessages = [...filteredMessages, { role: 'assistant', text: report, isReport: true }]
        localUpdateState({ messages: newMessages, loading: false, progress: '', streaming: false })
        return
      }

      if (type === 'voice_input_result') {
        const voiceText = text || ''
        const voiceError = error || ''
        if (voiceText && !voiceText.startsWith('语音识别') && !voiceText.includes('未识别')) {
          setInput('')
          const requestId = `req_${Date.now()}_${Math.random().toString(36).slice(2, 9)}`
          console.log("[语音发送] 识别文本:", voiceText, "请求ID:", requestId)
          const newMessages = [...currentState.messages, { role: 'user', text: voiceText, requestId }]
          streamBufferRef.current = ''
          localUpdateState({ messages: newMessages, loading: true, streaming: false })
          wsManager.send({ type: 'message', conversation_id: cid, content: voiceText, request_id: requestId })
        } else if (voiceError) {
          const newMessages = [...currentState.messages, { role: 'system', text: '❌ ' + voiceError }]
          localUpdateState({ messages: newMessages })
        } else if (!voiceText || voiceText.includes('未识别')) {
          const newMessages = [...currentState.messages, { role: 'system', text: '❌ 未识别到语音内容，请重试' }]
          localUpdateState({ messages: newMessages })
        }
        activeRequestIdsRef.current.delete(request_id)
        return
      }

      if (type === 'voice_output') {
        const audio = event.data.audio || ''
        if (audio) {
          playAudio(audio)
        }
        return
      }

      if (type === 'error' && message) {
        const newMessages = [...currentState.messages, { role: 'system', text: '❌ ' + message }]
        activeRequestIdsRef.current.delete(request_id)
        localUpdateState({ messages: newMessages, loading: false, progress: '', streaming: false })
        sendLockRef.current = false
        clearStuckTimer()
        return
      }

      if (type === 'progress' && progressText) {
        localUpdateState({ progress: progressText })
      } else if (type === 'thinking') {
        if (showThinking) {
          try {
            const data = JSON.parse(content)
            const newMessages = [...currentState.messages, {
              role: 'system',
              text: `🧠 **${data.tool || '思考'}**\n${data.input || data.status || data.progress || ''}\n${data.output ? '→ ' + data.output : ''}`,
              isThinking: true
            }]
            localUpdateState({ messages: newMessages })
          } catch (e) {}
        }
        // thinking 消息不阻止其他处理，继续往下
      } else if (type === 'stream_token' && content) {
        if (localState.progress) {
          localUpdateState({ progress: '' })
        }
        const newBuffer = streamBufferRef.current + content
        const last = currentState.messages[currentState.messages.length - 1]
        if (last && last.role === 'assistant' && last.streaming) {
          if (last.text === newBuffer) return
        }
        streamBufferRef.current = newBuffer
        let newMessages = [...currentState.messages]
        if (last && last.role === 'assistant' && last.streaming) {
          newMessages[newMessages.length - 1] = {
            ...last,
            text: streamBufferRef.current
          }
        } else {
          newMessages.push({ role: 'assistant', text: streamBufferRef.current, streaming: true })
        }
        localUpdateState({ messages: newMessages })
      }

      if (stuckTimerRef.current) {
        clearTimeout(stuckTimerRef.current)
      }
      stuckTimerRef.current = setTimeout(() => {
        const s = getState(cid)
        if (s && s.loading) {
          console.warn('[超时] 请求超过 60 秒未响应')
          localUpdateState({ progress: '⚠️ 请求时间较长，请耐心等待...' })
        }
      }, 60000)
    })
  }, [cid, onRefresh, localUpdateState, clearStuckTimer])

  useEffect(() => {
    msgsEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [localState?.messages.length, localState?.loading])

  const send = useCallback(() => {
    if (!input.trim() || !localState || localState.loading || sendLockRef.current) return

    sendLockRef.current = true
    const text = input.trim()
    const requestId = `req_${Date.now()}_${Math.random().toString(36).slice(2, 9)}`
    setInput('')

    if (activeRequestIdsRef.current.has(requestId)) return
    activeRequestIdsRef.current.add(requestId)

    const newMessages = [...localState.messages, { role: 'user', text, requestId }]
    streamBufferRef.current = ''
    localUpdateState({ messages: newMessages, loading: true, streaming: false })

    const resetTimeout = () => {
      if (stuckTimerRef.current) {
        clearTimeout(stuckTimerRef.current)
      }
      stuckTimerRef.current = setTimeout(() => {
        const s = getState(cid)
        if (s && s.loading) {
          console.warn('[超时] 请求超过 60 秒未响应，重置状态')
          const newMsgs = [...s.messages, { role: 'system', text: '⏰ 请求超时，请重试' }]
          localUpdateState({ messages: newMsgs, loading: false, progress: '', streaming: false })
          activeRequestIdsRef.current.delete(requestId)
        }
      }, 60000)
    }

    resetTimeout()

    wsManager.send({ type: 'message', message: text, conversation_id: cid, request_id: requestId })
  }, [input, localState, cid, localUpdateState])

  const generateReport = useCallback(() => {
    if (!localState || localState.loading || sendLockRef.current) return
    if (!localState.messages || localState.messages.length === 0) {
      const newMessages = [...localState.messages, { role: 'system', text: '请先进行对话，然后再生成报告' }]
      localUpdateState({ messages: newMessages })
      return
    }

    sendLockRef.current = true
    const requestId = `req_${Date.now()}_${Math.random().toString(36).slice(2, 9)}`
    
    activeRequestIdsRef.current.add(requestId)
    streamBufferRef.current = ''
    localUpdateState({ loading: true, progress: '📊 正在生成健康报告...' })

    const resetTimeout = () => {
      if (stuckTimerRef.current) {
        clearTimeout(stuckTimerRef.current)
      }
      stuckTimerRef.current = setTimeout(() => {
        const s = getState(cid)
        if (s && s.loading) {
          console.warn('[超时] 生成报告超过 60 秒未响应')
          localUpdateState({ progress: '⚠️ 生成报告时间较长，请耐心等待...' })
        }
      }, 60000)
    }

    resetTimeout()

    wsManager.send({ type: 'generate_report', conversation_id: cid, request_id: requestId })
  }, [localState, cid, localUpdateState])

  const startRecording = async () => {
    if (isRecording || localState?.loading) return
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          sampleRate: 16000,
          channelCount: 1,
          echoCancellation: true,
          noiseSuppression: true
        }
      })
      mediaRecorderRef.current = new MediaRecorder(stream)
      audioChunksRef.current = []

      mediaRecorderRef.current.ondataavailable = (event) => {
        if (event.data.size > 0) {
          audioChunksRef.current.push(event.data)
        }
      }

      mediaRecorderRef.current.onstop = async () => {
        const audioBlob = new Blob(audioChunksRef.current, { type: 'audio/webm' })
        console.log(`[录音调试] Blob 大小: ${audioBlob.size} 字节`)

        if (audioBlob.size < 2000) {
          const newMessages = [...localState.messages, { role: 'system', text: '❌ 请按住麦克风说话至少 1 秒钟' }]
          localUpdateState({ messages: newMessages })
          audioChunksRef.current = []
          return
        }

        const arrayBuffer = await audioBlob.arrayBuffer()
        const bytes = new Uint8Array(arrayBuffer)
        const base64 = btoa(String.fromCharCode(...bytes))
        console.log(`[录音调试] Base64 长度: ${base64.length}, 发送中...`)

        const requestId = `req_${Date.now()}_${Math.random().toString(36).slice(2, 9)}`
        activeRequestIdsRef.current.add(requestId)
        wsManager.send({ type: 'voice_input', audio: base64, conversation_id: cid, request_id: requestId })

        audioChunksRef.current = []
      }

      mediaRecorderRef.current.start()
      setIsRecording(true)
    } catch (err) {
      console.error('录音失败:', err)
      alert('无法访问麦克风，请检查权限设置')
    }
  }

  const stopRecording = () => {
    if (!isRecording || !mediaRecorderRef.current) return
    mediaRecorderRef.current.stop()
    mediaRecorderRef.current.stream.getTracks().forEach(track => track.stop())
    setIsRecording(false)
  }

  const playAudio = (base64Audio) => {
    try {
      const audioBytes = atob(base64Audio)
      const arrayBuffer = new ArrayBuffer(audioBytes.length)
      const uint8Array = new Uint8Array(arrayBuffer)
      for (let i = 0; i < audioBytes.length; i++) {
        uint8Array[i] = audioBytes.charCodeAt(i)
      }
      const audioBlob = new Blob([arrayBuffer], { type: 'audio/mp3' })
      const audioUrl = URL.createObjectURL(audioBlob)
      const audio = new Audio(audioUrl)
      audio.play()
      audio.onended = () => URL.revokeObjectURL(audioUrl)
    } catch (err) {
      console.error('播放音频失败:', err)
    }
  }

  const currentTTSAudioRef = useRef(null);
  const ttsStoppedRef = useRef(false);

  const playTTS = useCallback(async (text) => {
    if (!voiceEnabled) {
      console.log('[TTS调试] 语音播报未启用');
      return;
    }
    if (ttsStoppedRef.current) {
      console.log('[TTS调试] 播放已被用户停止');
      return;
    }
    console.log('[TTS调试] 开始请求流式TTS，文本长度:', text.length);

    if (currentTTSAudioRef.current) {
      console.log('[TTS调试] 清理上一次播放');
      currentTTSAudioRef.current.pause();
      currentTTSAudioRef.current.src = '';
      currentTTSAudioRef.current = null;
    }

    let audioQueue = [];
    let currentAudio = null;
    let isStopped = false;

    const playNext = () => {
      if (ttsStoppedRef.current) {
        console.log('[TTS调试] 播放队列被停止');
        isStopped = true;
        return;
      }
      if (isStopped || audioQueue.length === 0) {
        console.log('[TTS调试] 播放结束或队列为空');
        currentAudio = null;
        currentTTSAudioRef.current = null;
        return;
      }
      const audioData = audioQueue.shift();
      console.log('[TTS调试] 开始播放音频段，长度:', audioData.length);
      const audio = new Audio(`data:audio/mp3;base64,${audioData}`);
      currentAudio = audio;
      currentTTSAudioRef.current = audio;
      audio.onended = () => {
        console.log('[TTS调试] 音频段播放结束，播放下一个');
        playNext();
      };
      audio.play().then(() => {
        console.log('[TTS调试] 音频开始播放成功');
      }).catch(err => {
        console.warn('[TTS调试] 播放失败:', err.name, err.message);
        playNext();
      });
    };

    try {
      console.log('[TTS调试] 发起 fetch 请求...');
      const response = await fetch(`${API_BASE}/api/tts/stream`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text })
      });

      console.log('[TTS调试] 响应状态:', response.status, response.headers.get('content-type'));
      if (!response.ok) throw new Error(`HTTP ${response.status}`);

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) {
          console.log('[TTS调试] 流读取完毕');
          break;
        }

        const rawChunk = decoder.decode(value, { stream: true });
        console.log('[TTS调试] 原始数据块:', rawChunk);
        buffer += rawChunk;
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            const data = line.substring(6).trim();
            console.log('[TTS调试] 收到SSE数据:', data);
            if (data === '[DONE]') {
              console.log('[TTS调试] 收到结束标记');
              continue;
            }
            try {
              const parsed = JSON.parse(data);
              if (parsed.audio) {
                console.log('[TTS调试] 音频块入队，索引:', parsed.index, '文本:', parsed.text);
                audioQueue.push(parsed.audio);
                if (!currentAudio) {
                  console.log('[TTS调试] 当前无播放，立即开始');
                  playNext();
                }
              } else {
                console.warn('[TTS调试] 解析的JSON中无音频数据:', parsed);
              }
            } catch (e) {
              console.warn('[TTS调试] SSE数据解析失败:', data, e);
            }
          }
        }
      }

      if (buffer.startsWith('data: ')) {
        const data = buffer.substring(6).trim();
        console.log('[TTS调试] 处理缓冲区残留:', data);
        if (data !== '[DONE]') {
          try {
            const parsed = JSON.parse(data);
            if (parsed.audio) {
              audioQueue.push(parsed.audio);
              if (!currentAudio) playNext();
            }
          } catch (e) {}
        }
      }
    } catch (error) {
      console.error('[TTS调试] 流式请求失败，尝试完整音频:', error);
      try {
        const resp = await fetch(`${API_BASE}/api/tts`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ text })
        });
        console.log('[TTS调试] 降级响应状态:', resp.status);
        if (resp.ok) {
          const data = await resp.json();
          if (data.audio) {
            console.log('[TTS调试] 降级音频长度:', data.audio.length);
            if (ttsStoppedRef.current) {
              console.log('[TTS调试] 播放已被用户停止，跳过降级播放');
              return;
            }
            const audio = new Audio(`data:audio/mp3;base64,${data.audio}`);
            audio.play().then(() => {
              console.log('[TTS调试] 降级音频播放成功');
            }).catch(err => {
              console.error('[TTS调试] 降级音频播放失败:', err);
            });
            currentAudio = audio;
            currentTTSAudioRef.current = audio;
          } else {
            console.error('[TTS调试] 降级响应中无音频数据');
          }
        }
      } catch (fallbackError) {
        console.error('[TTS调试] 完整音频也失败:', fallbackError);
      }
    }
  }, [voiceEnabled]);

  const handleUpload = async (e) => {
    const file = e.target.files?.[0]
    if (!file || !localState) return
    const allowed = ['application/pdf', 'image/png', 'image/jpeg', 'image/jpg']
    if (!allowed.includes(file.type)) {
      const newMessages = [...localState.messages, { role: 'user', text: '不支持的文件类型，请上传 PDF、PNG 或 JPG' }]
      localUpdateState({ messages: newMessages })
      return
    }
    if (file.size > 10 * 1024 * 1024) {
      const newMessages = [...localState.messages, { role: 'user', text: '文件过大，请小于 10MB' }]
      localUpdateState({ messages: newMessages })
      return
    }

    const newMessages1 = [...localState.messages, { role: 'user', text: `📄 正在上传: ${file.name}...` }]
    localUpdateState({ messages: newMessages1, loading: true })

    try {
      const fd = new FormData()
      fd.append('file', file)
      const res = await fetch(`${API_BASE}/api/upload`, { method: 'POST', body: fd })
      const data = await res.json()

      if (data.success) {
        let msg = `✅ 文件上传成功！\n📄 ${data.file_name}`
        if (data.extracted_text) {
          msg += `\n\n📝 提取内容:\n${data.extracted_text.substring(0, 300)}${data.extracted_text.length > 300 ? '...' : ''}`
        }
        const currentMessages = (getState(cid)?.messages || localState.messages)
          .filter(m => !(m.role === 'user' && m.text && m.text.startsWith('📄 正在上传:')))
        const newMessages2 = [...currentMessages, { role: 'user', text: msg }]
        if (data.extracted_text?.length > 20) {
          const reportMsg = `[用户上传了检查报告]\n报告内容：\n${data.extracted_text}\n\n请根据以上报告内容分析用户的健康状况。`
          const requestId = `req_${Date.now()}_${Math.random().toString(36).slice(2, 9)}`
          if (!activeRequestIdsRef.current.has(requestId)) {
            activeRequestIdsRef.current.add(requestId)

            if (wsManager.ws?.readyState !== WebSocket.OPEN) {
              await new Promise((resolve) => {
                wsManager.connect()
                const onOpen = () => {
                  wsManager.ws.removeEventListener('open', onOpen)
                  resolve()
                }
                wsManager.ws.addEventListener('open', onOpen)
              })
            }

            wsManager.send({ type: 'message', message: reportMsg, conversation_id: cid, request_id: requestId })
            localUpdateState({
              messages: newMessages2,
              uploaded: { file_id: data.file_id, file_name: data.file_name, file_type: data.file_type, extracted_text: data.extracted_text },
              loading: true
            })
            streamBufferRef.current = ''

            if (stuckTimerRef.current) {
              clearTimeout(stuckTimerRef.current)
            }
            stuckTimerRef.current = setTimeout(() => {
              const s = getState(cid)
              if (s && s.loading) {
                console.warn('[超时] 文件上传后分析超过 60 秒未响应')
                const newMsgs = [...s.messages, { role: 'user', text: '⏰ 请求超时，请重试' }]
                localUpdateState({ messages: newMsgs, loading: false, progress: '', streaming: false })
                activeRequestIdsRef.current.delete(requestId)
              }
            }, 60000)
          }
        } else {
          localUpdateState({
            messages: newMessages2,
            uploaded: { file_id: data.file_id, file_name: data.file_name, file_type: data.file_type, extracted_text: data.extracted_text },
            loading: false
          })
        }
      } else {
        const currentState = getState(cid)
        const newMessages2 = [...currentState.messages, { role: 'user', text: `❌ 上传失败: ${data.detail || '未知错误'}` }]
        localUpdateState({ messages: newMessages2, loading: false })
      }
    } catch {
      const currentState = getState(cid)
      const newMessages2 = [...currentState.messages, { role: 'user', text: '上传失败，请检查网络连接' }]
      localUpdateState({ messages: newMessages2, loading: false })
    }
    e.target.value = ''
  }

  if (!localState && cid) {
    return (
      <div className="flex-1 flex items-center justify-center text-gray-400 dark:text-gray-500">
        请选择或新建对话
      </div>
    )
  }

  return (
    <div className="flex-1 flex flex-col min-h-0" onClick={() => setShowDownloadOptions(false)}>
      <div className="flex-1 overflow-y-auto px-4 py-6">
        <div className="max-w-3xl mx-auto space-y-4">
          {(!localState?.messages || localState.messages.length === 0) && !localState?.loading && (
            <div className="flex flex-col items-center justify-center py-20 text-gray-400 dark:text-gray-500">
              <svg className="w-16 h-16 mb-4 text-blue-300 dark:text-blue-700" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M4.318 6.318a4.5 4.5 0 000 6.364L12 20.364l7.682-7.682a4.5 4.5 0 00-6.364-6.364L12 7.636l-1.318-1.318a4.5 4.5 0 00-6.364 0z" />
              </svg>
              <p className="text-lg font-medium mb-1">智能健康助手</p>
              <p className="text-sm">描述您的症状，我将为您提供健康评估和建议</p>
            </div>
          )}

          {localState?.messages.map((msg, i) => (
            <div key={i} className={`flex message-enter ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
              {msg.role !== 'user' && (
                <div className="w-8 h-8 rounded-full bg-blue-100 dark:bg-blue-900/50 flex items-center justify-center shrink-0 mr-2 mt-1">
                  <svg className="w-5 h-5 text-blue-600 dark:text-blue-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4.318 6.318a4.5 4.5 0 000 6.364L12 20.364l7.682-7.682a4.5 4.5 0 00-6.364-6.364L12 7.636l-1.318-1.318a4.5 4.5 0 00-6.364 0z" />
                  </svg>
                </div>
              )}
              <div className={`max-w-[80%] rounded-2xl px-4 py-3 ${
                msg.role === 'user'
                  ? 'bg-blue-500 dark:bg-indigo-600 text-white'
                  : msg.role === 'system'
                    ? 'bg-gray-100 dark:bg-gray-800 text-gray-500 dark:text-gray-400 text-sm italic'
                    : msg.isThinking
                      ? 'bg-gray-50 dark:bg-[#1a1a3a] text-gray-400 dark:text-gray-500 text-xs border border-dashed border-gray-300 dark:border-gray-700'
                      : msg.isReport
                        ? 'bg-white dark:bg-[#1e1e3a] border border-gray-200 dark:border-[#2a2a5a] shadow-sm'
                        : 'bg-gray-100 dark:bg-[#252550] text-gray-900 dark:text-gray-100'
              }`}>
                {msg.isThinking ? (
                  <div className="whitespace-pre-wrap leading-relaxed opacity-80"><Markdown text={msg.text} /></div>
                ) : msg.isReport ? (
                  <div>
                    <div className="markdown-body text-sm"><Markdown text={msg.text} /></div>
                    <div className="mt-4 pt-4 border-t border-gray-200 dark:border-gray-700 relative">
                      <button
                        onClick={(e) => { e.stopPropagation(); setShowDownloadOptions(!showDownloadOptions) }}
                        className="px-4 py-2 text-sm bg-blue-500 text-white rounded-lg hover:bg-blue-600 flex items-center gap-2"
                      >
                        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
                        </svg>
                        预览 / 下载
                      </button>
                      {showDownloadOptions && (
                        <div className="absolute left-0 mt-2 w-48 bg-white dark:bg-[#252550] border border-gray-200 dark:border-gray-700 rounded-xl shadow-lg z-10">
                          <button
                            onClick={() => { setMdPreview(msg.text); setShowDownloadOptions(false) }}
                            className="w-full text-left px-4 py-3 hover:bg-gray-100 dark:hover:bg-gray-800 rounded-t-xl flex items-center gap-2 text-sm"
                          >
                            <span className="text-blue-500">📝</span> 预览 MD
                          </button>
                          <button
                            onClick={() => { window.open(`${API_BASE}/api/history/${cid}/download?format=pdf&preview=true`, '_blank'); setShowDownloadOptions(false) }}
                            className="w-full text-left px-4 py-3 hover:bg-gray-100 dark:hover:bg-gray-800 flex items-center gap-2 text-sm"
                          >
                            <span className="text-red-500">📄</span> 预览 PDF
                          </button>
                          <button
                            onClick={() => { window.open(`${API_BASE}/api/history/${cid}/download?format=docx`, '_blank'); setShowDownloadOptions(false) }}
                            className="w-full text-left px-4 py-3 hover:bg-gray-100 dark:hover:bg-gray-800 rounded-b-xl flex items-center gap-2 text-sm"
                          >
                            <span className="text-green-500">📃</span> 下载 Word
                          </button>
                        </div>
                      )}
                    </div>
                  </div>
                ) : msg.role === 'user' ? (
                  <p className="text-sm whitespace-pre-wrap">{msg.text}</p>
                ) : (
                  <div className={`text-sm ${hasMarkdown(msg.text) ? 'markdown-body' : 'whitespace-pre-wrap'}`}>
                    {hasMarkdown(msg.text) ? (
                      <Markdown text={msg.text} />
                    ) : (
                      <p className={`${msg.streaming ? 'stream-cursor' : ''}`}>{msg.text}</p>
                    )}
                    {msg.streaming && <span className="stream-cursor" />}
                  </div>
                )}
              </div>
              {msg.role === 'user' && (
                <div className="w-8 h-8 rounded-full bg-blue-500 dark:bg-indigo-600 flex items-center justify-center shrink-0 ml-2 mt-1">
                  <svg className="w-5 h-5 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
                  </svg>
                </div>
              )}
            </div>
          ))}

          {localState?.loading && (
            <div className="flex justify-start message-enter">
              <div className="w-8 h-8 rounded-full bg-blue-100 dark:bg-blue-900/50 flex items-center justify-center shrink-0 mr-2 mt-1">
                <svg className="w-5 h-5 text-blue-600 dark:text-blue-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4.318 6.318a4.5 4.5 0 000 6.364L12 20.364l7.682-7.682a4.5 4.5 0 00-6.364-6.364L12 7.636l-1.318-1.318a4.5 4.5 0 00-6.364 0z" />
                </svg>
              </div>
              <div className="bg-gray-100 dark:bg-[#252550] rounded-2xl px-4 py-3 flex items-center gap-2">
                <div className="flex gap-1">
                  <div className="w-2 h-2 bg-blue-500 dark:bg-blue-400 rounded-full typing-dot" />
                  <div className="w-2 h-2 bg-blue-500 dark:bg-blue-400 rounded-full typing-dot" />
                  <div className="w-2 h-2 bg-blue-500 dark:bg-blue-400 rounded-full typing-dot" />
                </div>
                {localState.progress && <span className="text-sm text-gray-500 dark:text-gray-400">{localState.progress}</span>}
              </div>
            </div>
          )}
          <div ref={msgsEndRef} />
        </div>
      </div>

      <div className="p-4 bg-white dark:bg-[#1a1a2e] border-t border-gray-200 dark:border-[#2a2a5a]">
        <div className="max-w-3xl mx-auto">
          <div className="flex gap-2 items-end">
            <label className="p-3 text-gray-400 hover:text-blue-500 dark:hover:text-blue-400 cursor-pointer transition-colors shrink-0">
              <input type="file" accept=".pdf,.png,.jpg,.jpeg" onChange={handleUpload} className="hidden" disabled={localState?.loading} />
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15.172 7l-6.586 6.586a2 2 0 102.828 2.828l6.414-6.586a4 4 0 00-5.656-5.656l-6.415 6.585a6 6 0 108.486 8.486L20.5 13" />
              </svg>
            </label>

            <button
              onMouseDown={startRecording}
              onMouseUp={stopRecording}
              onMouseLeave={stopRecording}
              onTouchStart={(e) => { e.preventDefault(); startRecording() }}
              onTouchEnd={(e) => { e.preventDefault(); stopRecording() }}
              disabled={localState?.loading}
              className={`p-3 rounded-xl transition-colors disabled:opacity-40 disabled:cursor-not-allowed shrink-0 ${
                isRecording
                  ? 'bg-red-500 text-white animate-pulse'
                  : 'text-gray-400 hover:text-blue-500 dark:hover:text-blue-400'
              }`}>
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                {isRecording ? (
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                ) : (
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z" />
                )}
              </svg>
            </button>

            <div className="flex-1 relative">
              <textarea
                ref={inputRef}
                value={input}
                onChange={e => setInput(e.target.value)}
                onKeyDown={e => {
                  if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault()
                    send()
                  }
                }}
                placeholder="描述您的症状或不适..."
                disabled={localState?.loading}
                rows={1}
                className="w-full px-4 py-3 border border-gray-300 dark:border-[#2a2a5a] rounded-xl
                  bg-white dark:bg-[#252550] text-gray-900 dark:text-gray-100
                  focus:ring-2 focus:ring-blue-500 focus:border-transparent outline-none
                  disabled:opacity-50 resize-none placeholder-gray-400 dark:placeholder-gray-500 text-sm"
                style={{ minHeight: '44px', maxHeight: '120px' }}
                onInput={e => {
                  e.target.style.height = 'auto'
                  e.target.style.height = Math.min(e.target.scrollHeight, 120) + 'px'
                }}
              />
            </div>

            <button
              onClick={send}
              disabled={!input.trim() || localState?.loading}
              className="p-3 bg-blue-500 hover:bg-blue-600 dark:bg-indigo-600 dark:hover:bg-indigo-500
                text-white rounded-xl transition-colors disabled:opacity-40 disabled:cursor-not-allowed shrink-0">
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8" />
              </svg>
            </button>

            <button
              onClick={generateReport}
              disabled={!localState?.messages?.length || localState?.loading}
              className="px-4 py-3 bg-green-500 hover:bg-green-600 dark:bg-green-600 dark:hover:bg-green-500
                text-white rounded-xl transition-colors disabled:opacity-40 disabled:cursor-not-allowed shrink-0 text-sm font-medium flex items-center gap-2">
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
              </svg>
              生成报告
            </button>

            <button
              onClick={() => {
                if (voiceEnabled) {
                  ttsStoppedRef.current = true;
                  if (currentTTSAudioRef.current) {
                    try {
                      currentTTSAudioRef.current.pause();
                      currentTTSAudioRef.current.src = '';
                    } catch (_) {}
                    currentTTSAudioRef.current = null;
                  }
                } else {
                  ttsStoppedRef.current = false;
                }
                setVoiceEnabled(!voiceEnabled);
              }}
              className={`p-3 rounded-xl transition-colors shrink-0 ${
                voiceEnabled
                  ? 'bg-purple-500 text-white'
                  : 'text-gray-400 hover:text-purple-500 dark:hover:text-purple-400'
              }`}
              title={voiceEnabled ? '关闭语音播报' : '开启语音播报'}>
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                {voiceEnabled ? (
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15.536 8.464a5 5 0 010 7.072m2.828-9.9a9 9 0 010 12.728M5.586 15H4a1 1 0 01-1-1v-4a1 1 0 011-1h1.586l4.707-4.707C10.923 3.663 12 4.109 12 5v14c0 .891-1.077 1.337-1.707.707L5.586 15z" />
                ) : (
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15.536 8.464a5 5 0 010 7.072m2.828-9.9a9 9 0 010 12.728M5.586 15H4a1 1 0 01-1-1v-4a1 1 0 011-1h1.586l4.707-4.707C10.923 3.663 12 4.109 12 5v14c0 .891-1.077 1.337-1.707.707L5.586 15z" />
                )}
              </svg>
            </button>

            <button
              onClick={() => setShowThinking(!showThinking)}
              className={`p-3 rounded-xl transition-colors shrink-0 ${
                showThinking
                  ? 'bg-indigo-500 text-white'
                  : 'text-gray-400 hover:text-indigo-500 dark:hover:text-indigo-400'
              }`}
              title={showThinking ? '隐藏思考过程' : '查看思考过程'}>
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
              </svg>
            </button>
          </div>

          {localState?.uploaded && (
            <div className="flex items-center gap-2 mt-2 text-sm text-gray-500 dark:text-gray-400">
              <svg className="w-4 h-4 text-green-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
              </svg>
              已上传: {localState.uploaded.file_name}
            </div>
          )}

          <p className="text-center text-xs text-gray-400 dark:text-gray-600 mt-2">
            本助手提供健康参考，不能替代专业医生的诊断。紧急情况请立即就医。
          </p>
        </div>
      </div>

      {mdPreview && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50" onClick={() => setMdPreview(null)}>
          <div className="bg-white dark:bg-[#1e1e3a] rounded-2xl shadow-2xl max-w-3xl w-full mx-4 max-h-[90vh] flex flex-col"
               onClick={e => e.stopPropagation()}>
            <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200 dark:border-gray-700">
              <h3 className="text-lg font-bold">报告预览 (Markdown)</h3>
              <button onClick={() => setMdPreview(null)} className="p-2 hover:bg-gray-100 dark:hover:bg-gray-800 rounded-lg">
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>
            <div className="flex-1 overflow-y-auto px-6 py-4 markdown-body text-sm">
              <Markdown text={mdPreview} />
            </div>
            <div className="px-6 py-4 border-t border-gray-200 dark:border-gray-700 flex gap-3 justify-end">
              <button onClick={() => window.open(`${API_BASE}/api/history/${cid}/download?format=md`)}
                className="px-4 py-2 text-sm bg-blue-500 text-white rounded-lg hover:bg-blue-600">
                下载 MD
              </button>
              <button onClick={() => setMdPreview(null)}
                className="px-4 py-2 text-sm bg-gray-300 text-gray-700 rounded-lg hover:bg-gray-400">
                关闭
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

function DetailPage({ reportId, onBack, dark }) {
  const [content, setContent] = useState(null)

  useEffect(() => {
    (async () => {
      try {
        const res = await fetch(`${API_BASE}/api/history/${reportId}`)
        const data = await res.json()
        if (data.data) setContent(data.data)
      } catch {}
    })()
  }, [reportId])

  return (
    <div className="flex-1 overflow-y-auto p-6">
      <div className="max-w-3xl mx-auto">
        <button onClick={onBack} className="mb-4 flex items-center gap-2 text-blue-500 hover:text-blue-600 text-sm">
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
          </svg>
          返回
        </button>
        {content ? (
          <div className="bg-white dark:bg-[#1e1e3a] rounded-xl p-6 border border-gray-200 dark:border-[#2a2a5a]">
            <h2 className="text-xl font-bold mb-4">{content.title || '报告详情'}</h2>
            {content.health_reports?.map(r => (
              <div key={r.id} className="markdown-body text-sm"><Markdown text={r.content_markdown || ''} /></div>
            ))}
          </div>
        ) : (
          <div className="flex items-center justify-center py-20 text-gray-400">加载中...</div>
        )}
      </div>
    </div>
  )
}
