import { useState, useEffect } from 'react'

const API_BASE = 'http://localhost:8000'

export default function HistoryDetailPage({ conversationId, onBack }) {
  const [conversation, setConversation] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    fetchDetail()
  }, [conversationId])

  const fetchDetail = async () => {
    setLoading(true)
    try {
      const res = await fetch(`${API_BASE}/api/history/${conversationId}`)
      const data = await res.json()
      if (data.success) {
        setConversation(data.data)
      }
    } catch (e) {
      console.error('获取详情失败:', e)
    }
    setLoading(false)
  }

  const formatDate = (dateStr) => {
    return new Date(dateStr).toLocaleString('zh-CN')
  }

  const renderReport = (text) => {
    if (!text) return null
    const lines = text.split('\n')
    return lines.map((line, i) => {
      if (line.startsWith('### ')) return <h3 key={i} className="text-lg font-bold mt-4 mb-2">{line.replace('### ', '')}</h3>
      if (line.startsWith('## ')) return <h2 key={i} className="text-xl font-bold mt-4 mb-2 border-b pb-1">{line.replace('## ', '')}</h2>
      if (line.startsWith('# ')) return <h1 key={i} className="text-2xl font-bold mt-4 mb-2">{line.replace('# ', '')}</h1>
      if (line.startsWith('|')) return <pre key={i} className="text-xs overflow-x-auto">{line}</pre>
      if (line.startsWith('- ')) return <li key={i} className="ml-4 text-sm">{line.replace('- ', '')}</li>
      if (line.startsWith('> ')) return <blockquote key={i} className="border-l-4 border-yellow-400 pl-3 text-sm italic my-2">{line.replace('> ', '')}</blockquote>
      if (line.trim() === '') return <br key={i} />
      return <p key={i} className="text-sm my-1">{line}</p>
    })
  }

  if (loading) {
    return (
      <div className="flex flex-col h-screen bg-gray-50">
        <header className="bg-white shadow px-6 py-4 flex items-center gap-3">
          <button onClick={onBack} className="text-gray-600 hover:text-gray-800">
            <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
            </svg>
          </button>
          <h1 className="text-lg font-bold text-gray-800">加载中...</h1>
        </header>
        <div className="flex-1 flex items-center justify-center">
          <div className="animate-spin w-8 h-8 border-4 border-blue-500 border-t-transparent rounded-full"></div>
        </div>
      </div>
    )
  }

  if (!conversation) {
    return (
      <div className="flex flex-col h-screen bg-gray-50">
        <header className="bg-white shadow px-6 py-4 flex items-center gap-3">
          <button onClick={onBack} className="text-gray-600 hover:text-gray-800">
            <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
            </svg>
          </button>
          <h1 className="text-lg font-bold text-gray-800">会话不存在</h1>
        </header>
      </div>
    )
  }

  return (
    <div className="flex flex-col h-screen bg-gray-50">
      {/* 头部 */}
      <header className="bg-white shadow px-6 py-4 flex items-center gap-3">
        <button onClick={onBack} className="text-gray-600 hover:text-gray-800">
          <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
          </svg>
        </button>
        <div className="flex-1">
          <h1 className="text-lg font-bold text-gray-800">{conversation.title}</h1>
          <p className="text-sm text-gray-500">{formatDate(conversation.created_at)}</p>
        </div>
        <span className={`text-xs px-3 py-1 rounded-full ${
          conversation.status === 'completed'
            ? 'bg-green-100 text-green-700'
            : 'bg-blue-100 text-blue-700'
        }`}>
          {conversation.status === 'completed' ? '已完成' : '进行中'}
        </span>
      </header>

      {/* 内容 */}
      <div className="flex-1 overflow-y-auto px-4 py-6">
        <div className="max-w-3xl mx-auto space-y-4">

          {/* 消息列表 */}
          {conversation.messages.map((msg, i) => (
            <div key={msg.id || i} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
              <div className={`max-w-[85%] rounded-2xl px-4 py-3 ${
                msg.role === 'user' ? 'bg-blue-500 text-white' : 'bg-white border shadow-sm'
              }`}>
                <p className="whitespace-pre-wrap text-sm">{msg.content}</p>
                <p className={`text-xs mt-1 ${msg.role === 'user' ? 'text-blue-100' : 'text-gray-400'}`}>
                  {formatDate(msg.created_at)}
                </p>
              </div>
            </div>
          ))}

          {/* 健康报告 */}
          {conversation.health_reports.length > 0 && (
            <div className="mt-6">
              <h2 className="text-lg font-bold text-gray-800 mb-3 flex items-center gap-2">
                <span>📄</span> 健康报告
              </h2>
              {conversation.health_reports.map((report, i) => (
                <div key={report.id} className="bg-white border shadow-sm rounded-2xl p-4">
                  {report.risk_level && (
                    <div className="mb-3">
                      <span className={`text-xs px-2 py-1 rounded-full ${
                        report.risk_level === 'high' ? 'bg-red-100 text-red-700' :
                        report.risk_level === 'medium' ? 'bg-yellow-100 text-yellow-700' :
                        'bg-green-100 text-green-700'
                      }`}>
                        风险等级: {report.risk_level === 'high' ? '高' : report.risk_level === 'medium' ? '中' : '低'}
                      </span>
                    </div>
                  )}
                  <div className="prose prose-sm max-w-none">
                    {renderReport(report.content_markdown)}
                  </div>
                  <p className="text-xs text-gray-400 mt-3">
                    生成时间: {formatDate(report.created_at)}
                  </p>
                </div>
              ))}
            </div>
          )}

          {/* 检查报告 */}
          {conversation.check_reports.length > 0 && (
            <div className="mt-6">
              <h2 className="text-lg font-bold text-gray-800 mb-3 flex items-center gap-2">
                <span>📋</span> 检查报告
              </h2>
              {conversation.check_reports.map((report, i) => (
                <div key={report.id} className="bg-white border shadow-sm rounded-2xl p-4">
                  <div className="flex items-center gap-2 mb-2">
                    <span className="text-sm font-medium text-gray-700">{report.filename}</span>
                    <span className="text-xs text-gray-400">({report.file_type})</span>
                  </div>
                  {report.analysis_result && (
                    <div className="text-sm text-gray-600 whitespace-pre-wrap">
                      {report.analysis_result}
                    </div>
                  )}
                  <p className="text-xs text-gray-400 mt-2">
                    上传时间: {formatDate(report.created_at)}
                  </p>
                </div>
              ))}
            </div>
          )}

          <div className="h-10"></div>
        </div>
      </div>
    </div>
  )
}
