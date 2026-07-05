import { useState, useEffect } from 'react'

const API_BASE = 'http://localhost:8000'

export default function HistoryPage({ onBack, onViewDetail }) {
  const [conversations, setConversations] = useState([])
  const [loading, setLoading] = useState(true)
  const [page, setPage] = useState(1)
  const [total, setTotal] = useState(0)
  const [stats, setStats] = useState({})
  const pageSize = 10

  useEffect(() => {
    fetchHistory()
    fetchStats()
  }, [page])

  const fetchHistory = async () => {
    setLoading(true)
    try {
      const res = await fetch(`${API_BASE}/api/history?page=${page}&page_size=${pageSize}`)
      const data = await res.json()
      if (data.success) {
        setConversations(data.data)
        setTotal(data.total)
      }
    } catch (e) {
      console.error('获取历史失败:', e)
    }
    setLoading(false)
  }

  const fetchStats = async () => {
    try {
      const res = await fetch(`${API_BASE}/api/history/stats/summary`)
      const data = await res.json()
      if (data.success) {
        setStats(data.data)
      }
    } catch (e) {
      console.error('获取统计失败:', e)
    }
  }

  const formatDate = (dateStr) => {
    const date = new Date(dateStr)
    const now = new Date()
    const diff = now - date
    const days = Math.floor(diff / (1000 * 60 * 60 * 24))

    if (days === 0) return '今天'
    if (days === 1) return '昨天'
    if (days < 7) return `${days}天前`
    return date.toLocaleDateString('zh-CN')
  }

  const totalPages = Math.ceil(total / pageSize)

  return (
    <div className="flex flex-col h-screen bg-gray-50">
      {/* 头部 */}
      <header className="bg-white shadow px-6 py-4 flex items-center gap-3">
        <button onClick={onBack} className="text-gray-600 hover:text-gray-800">
          <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
          </svg>
        </button>
        <div>
          <h1 className="text-lg font-bold text-gray-800">问诊历史</h1>
          <p className="text-sm text-gray-500">共 {total} 条记录</p>
        </div>
      </header>

      {/* 统计卡片 */}
      <div className="px-6 py-4">
        <div className="grid grid-cols-3 gap-4">
          <div className="bg-white rounded-xl p-4 shadow-sm">
            <div className="text-2xl font-bold text-blue-600">{stats.total || 0}</div>
            <div className="text-sm text-gray-500">总会话</div>
          </div>
          <div className="bg-white rounded-xl p-4 shadow-sm">
            <div className="text-2xl font-bold text-green-600">{stats.completed || 0}</div>
            <div className="text-sm text-gray-500">已完成</div>
          </div>
          <div className="bg-white rounded-xl p-4 shadow-sm">
            <div className="text-2xl font-bold text-orange-500">{stats.monthly || 0}</div>
            <div className="text-sm text-gray-500">本月</div>
          </div>
        </div>
      </div>

      {/* 历史列表 */}
      <div className="flex-1 overflow-y-auto px-6 pb-6">
        {loading ? (
          <div className="text-center py-10 text-gray-500">
            <div className="animate-spin w-8 h-8 border-4 border-blue-500 border-t-transparent rounded-full mx-auto mb-4"></div>
            加载中...
          </div>
        ) : conversations.length === 0 ? (
          <div className="text-center py-10 text-gray-500">
            <div className="text-5xl mb-4">📋</div>
            <p>暂无问诊记录</p>
          </div>
        ) : (
          <div className="space-y-3">
            {conversations.map((conv) => (
              <div
                key={conv.id}
                onClick={() => onViewDetail(conv.id)}
                className="bg-white rounded-xl p-4 shadow-sm hover:shadow-md transition-shadow cursor-pointer"
              >
                <div className="flex items-start justify-between">
                  <div className="flex-1">
                    <div className="flex items-center gap-2">
                      <h3 className="font-medium text-gray-800">{conv.title}</h3>
                      <span className={`text-xs px-2 py-0.5 rounded-full ${
                        conv.status === 'completed'
                          ? 'bg-green-100 text-green-700'
                          : 'bg-blue-100 text-blue-700'
                      }`}>
                        {conv.status === 'completed' ? '已完成' : '进行中'}
                      </span>
                    </div>
                    <p className="text-sm text-gray-500 mt-1">
                      {conv.message_count} 条消息
                    </p>
                  </div>
                  <div className="text-right">
                    <div className="text-sm text-gray-400">{formatDate(conv.updated_at)}</div>
                  </div>
                </div>
              </div>
            ))}

            {/* 分页 */}
            {totalPages > 1 && (
              <div className="flex justify-center gap-2 pt-4">
                <button
                  onClick={() => setPage(p => Math.max(1, p - 1))}
                  disabled={page === 1}
                  className="px-3 py-1 rounded bg-gray-200 disabled:opacity-50"
                >
                  上一页
                </button>
                <span className="px-3 py-1 text-gray-600">
                  {page} / {totalPages}
                </span>
                <button
                  onClick={() => setPage(p => Math.min(totalPages, p + 1))}
                  disabled={page === totalPages}
                  className="px-3 py-1 rounded bg-gray-200 disabled:opacity-50"
                >
                  下一页
                </button>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
