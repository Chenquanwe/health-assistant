import React, { useState, useEffect, useRef, useCallback } from 'react'

const API_BASE = 'http://localhost:8000'

const ACCEPTED_TYPES = ['application/pdf', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document', 'text/markdown', 'text/plain', 'image/png', 'image/jpeg', 'image/jpg']
const ACCEPTED_EXT = '.pdf,.docx,.md,.txt,.png,.jpg,.jpeg'

export default function KnowledgeManager({ dark }) {
  const [documents, setDocuments] = useState([])
  const [page, setPage] = useState(1)
  const [pageSize] = useState(50)
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [selectedFile, setSelectedFile] = useState(null)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const [isDragOver, setIsDragOver] = useState(false)
  const fileInputRef = useRef(null)

  const loadDocuments = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const res = await fetch(`${API_BASE}/api/knowledge/documents?page=${page}&page_size=${pageSize}`)
      const data = await res.json()
      console.log('[Knowledge] 文档列表加载:', data)
      if (data.success) {
        setDocuments(data.data || [])
        setTotal(data.total || 0)
      } else {
        setError(data.detail || '加载文档列表失败')
      }
    } catch (e) {
      console.error('[Knowledge] 加载文档列表异常:', e)
      setError('网络错误，请检查后端服务是否启动')
    } finally {
      setLoading(false)
    }
  }, [page, pageSize])

  useEffect(() => {
    loadDocuments()
  }, [loadDocuments])

  const handleFileSelect = (file) => {
    if (!file) return
    console.log('[Knowledge] 上传文件:', file.name, '大小:', file.size, '类型:', file.type)
    setSelectedFile(file)
    setError('')
    setMessage('')
  }

  const validateFile = (file) => {
    if (!file) return '请选择文件'
    if (ACCEPTED_TYPES.includes(file.type)) return ''
    const nameLower = file.name.toLowerCase()
    if (ACCEPTED_EXT.split(',').some(ext => nameLower.endsWith(ext))) return ''
    return `不支持的文件类型，仅支持 ${ACCEPTED_EXT}`
  }

  const handleUpload = async () => {
    if (!selectedFile) {
      setError('请先选择要上传的文件')
      return
    }
    const errMsg = validateFile(selectedFile)
    if (errMsg) {
      setError(errMsg)
      return
    }
    setUploading(true)
    setError('')
    setMessage('正在上传并处理...')
    try {
      const formData = new FormData()
      formData.append('file', selectedFile)
      console.log('[Knowledge] 开始上传:', selectedFile.name)
      const res = await fetch(`${API_BASE}/api/knowledge/upload`, {
        method: 'POST',
        body: formData,
      })
      const data = await res.json()
      console.log('[Knowledge] 上传响应:', data)
      if (res.ok && data.success) {
        setMessage(`上传成功：${data.title}，已分块 ${data.chunks} 条`)
        setSelectedFile(null)
        if (fileInputRef.current) fileInputRef.current.value = ''
        setPage(1)
        await loadDocuments()
      } else {
        setError(data.detail || data.message || '上传失败')
      }
    } catch (e) {
      console.error('[Knowledge] 上传异常:', e)
      setError('上传失败，请检查网络或后端服务')
    } finally {
      setUploading(false)
    }
  }

  const handleDelete = async (doc) => {
    if (!window.confirm(`确认删除文档「${doc.title || doc.filename}」吗？`)) return
    const docId = doc.id
    console.log('[Knowledge] 删除文档:', docId)
    try {
      const res = await fetch(`${API_BASE}/api/knowledge/documents/${encodeURIComponent(docId)}`, {
        method: 'DELETE',
      })
      const data = await res.json()
      console.log('[Knowledge] 删除响应:', data)
      if (res.ok && data.success) {
        setMessage(`已删除文档：${doc.title || doc.filename}`)
        // 删除后如果当前页删空，回退一页
        if (documents.length === 1 && page > 1) {
          setPage(p => p - 1)
        } else {
          await loadDocuments()
        }
      } else {
        setError(data.detail || data.message || '删除失败')
      }
    } catch (e) {
      console.error('[Knowledge] 删除异常:', e)
      setError('删除失败，请检查网络或后端服务')
    }
  }

  const onDrop = (e) => {
    e.preventDefault()
    setIsDragOver(false)
    const file = e.dataTransfer.files && e.dataTransfer.files[0]
    if (file) handleFileSelect(file)
  }

  const onDragOver = (e) => {
    e.preventDefault()
    setIsDragOver(true)
  }

  const onDragLeave = () => setIsDragOver(false)

  const totalPages = Math.max(1, Math.ceil(total / pageSize))

  const sizeLabel = (bytes) => {
    if (!bytes && bytes !== 0) return '-'
    if (bytes < 1024) return `${bytes} B`
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
    return `${(bytes / 1024 / 1024).toFixed(2)} MB`
  }

  return (
    <div className="flex-1 flex flex-col h-full overflow-hidden">
      <header className="px-6 py-3 border-b border-gray-200 dark:border-[#2a2a5a] flex items-center justify-between">
        <div className="flex items-center gap-3">
          <svg className="w-6 h-6 text-blue-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253" />
          </svg>
          <h1 className="text-lg font-semibold text-gray-800 dark:text-gray-100">知识库管理</h1>
        </div>
        <span className="text-sm text-gray-500 dark:text-gray-400">共 {total} 条文档</span>
      </header>

      <div className="flex-1 overflow-y-auto p-6 space-y-6">
        {/* 上传区域 */}
        <section className={`rounded-2xl border-2 border-dashed p-6 transition-colors
          ${isDragOver
            ? 'border-blue-500 bg-blue-50 dark:bg-blue-900/20'
            : 'border-gray-300 dark:border-[#2a2a5a] bg-white dark:bg-[#1a1a2e]'}
        `}>
          <div
            onDrop={onDrop}
            onDragOver={onDragOver}
            onDragLeave={onDragLeave}
            className="flex flex-col items-center justify-center gap-3 cursor-pointer min-h-[140px]"
            onClick={() => fileInputRef.current && fileInputRef.current.click()}
          >
            <svg className="w-10 h-10 text-gray-400 dark:text-gray-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
            </svg>
            <p className="text-sm text-gray-600 dark:text-gray-300">
              将文件拖拽到此处，或<span className="text-blue-500 font-medium mx-1">点击选择</span>文件
            </p>
            <p className="text-xs text-gray-400 dark:text-gray-500">
              支持 PDF、DOCX、MD、TXT、PNG、JPG、JPEG
            </p>
            {selectedFile && (
              <div className="mt-2 px-3 py-2 rounded-lg bg-gray-100 dark:bg-[#252550] text-sm text-gray-700 dark:text-gray-200 flex items-center gap-2 max-w-full">
                <svg className="w-4 h-4 shrink-0 text-blue-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                </svg>
                <span className="truncate">{selectedFile.name}</span>
                <span className="shrink-0 text-xs text-gray-500 dark:text-gray-400">({sizeLabel(selectedFile.size)})</span>
              </div>
            )}
          </div>

          <div className="mt-4 flex flex-wrap items-center gap-3">
            <input
              ref={fileInputRef}
              type="file"
              accept={ACCEPTED_EXT}
              className="hidden"
              onChange={(e) => handleFileSelect(e.target.files && e.target.files[0])}
            />
            <button
              onClick={handleUpload}
              disabled={uploading || !selectedFile}
              className="px-4 py-2 rounded-lg bg-blue-600 hover:bg-blue-700 disabled:bg-blue-400 disabled:cursor-not-allowed text-white text-sm font-medium transition-colors"
            >
              {uploading ? '正在上传并处理...' : '上传到知识库'}
            </button>
            <button
              onClick={() => { setSelectedFile(null); setError(''); setMessage(''); if (fileInputRef.current) fileInputRef.current.value = '' }}
              disabled={uploading}
              className="px-4 py-2 rounded-lg border border-gray-300 dark:border-[#2a2a5a] hover:bg-gray-100 dark:hover:bg-[#252550] text-gray-700 dark:text-gray-200 text-sm transition-colors"
            >
              清空选择
            </button>
            {message && (
              <span className="text-sm text-green-600 dark:text-green-400">{message}</span>
            )}
            {error && (
              <span className="text-sm text-red-600 dark:text-red-400">{error}</span>
            )}
          </div>
        </section>

        {/* 文档列表 */}
        <section className="rounded-2xl bg-white dark:bg-[#1a1a2e] border border-gray-200 dark:border-[#2a2a5a] overflow-hidden">
          <div className="px-4 py-3 border-b border-gray-200 dark:border-[#2a2a5a] flex items-center justify-between">
            <h2 className="text-sm font-semibold text-gray-700 dark:text-gray-200">文档列表</h2>
            <button
              onClick={loadDocuments}
              className="text-xs text-blue-500 hover:text-blue-600"
            >
              刷新
            </button>
          </div>

          {loading ? (
            <div className="p-6 text-center text-sm text-gray-500 dark:text-gray-400">加载中...</div>
          ) : documents.length === 0 ? (
            <div className="p-10 text-center text-sm text-gray-500 dark:text-gray-400">
              暂无知识文档，请上传
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="bg-gray-50 dark:bg-[#252550] text-gray-500 dark:text-gray-300">
                  <tr>
                    <th className="text-left px-4 py-2 font-medium">文件名</th>
                    <th className="text-left px-4 py-2 font-medium">大小</th>
                    <th className="text-left px-4 py-2 font-medium">分块</th>
                    <th className="text-left px-4 py-2 font-medium">状态</th>
                    <th className="text-left px-4 py-2 font-medium">上传时间</th>
                    <th className="text-right px-4 py-2 font-medium">操作</th>
                  </tr>
                </thead>
                <tbody>
                  {documents.map(doc => (
                    <tr key={doc.id} className="border-t border-gray-100 dark:border-[#2a2a5a] hover:bg-gray-50 dark:hover:bg-[#252550]/50">
                      <td className="px-4 py-2 text-gray-800 dark:text-gray-100 truncate max-w-[260px]" title={doc.title || doc.filename}>
                        {doc.title || doc.filename}
                      </td>
                      <td className="px-4 py-2 text-gray-600 dark:text-gray-300">{sizeLabel(doc.file_size)}</td>
                      <td className="px-4 py-2 text-gray-600 dark:text-gray-300">{doc.chunk_count ?? 0}</td>
                      <td className="px-4 py-2">
                        <span className={`inline-block px-2 py-0.5 rounded text-xs
                          ${doc.status === 'active' || doc.status === 'completed'
                            ? 'bg-green-100 text-green-700 dark:bg-green-900/40 dark:text-green-300'
                            : 'bg-yellow-100 text-yellow-700 dark:bg-yellow-900/40 dark:text-yellow-300'}`}>
                          {doc.status || 'unknown'}
                        </span>
                      </td>
                      <td className="px-4 py-2 text-gray-600 dark:text-gray-300 whitespace-nowrap">
                        {doc.created_at ? new Date(doc.created_at).toLocaleString('zh-CN') : '-'}
                      </td>
                      <td className="px-4 py-2 text-right">
                        <button
                          onClick={() => handleDelete(doc)}
                          className="px-3 py-1 rounded text-xs bg-red-500 hover:bg-red-600 text-white transition-colors"
                          title="删除文档"
                        >
                          删除
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {total > pageSize && (
            <div className="px-4 py-3 border-t border-gray-200 dark:border-[#2a2a5a] flex items-center justify-between">
              <span className="text-xs text-gray-500 dark:text-gray-400">
                第 {page} / {totalPages} 页，共 {total} 条
              </span>
              <div className="flex items-center gap-2">
                <button
                  onClick={() => setPage(p => Math.max(1, p - 1))}
                  disabled={page <= 1 || loading}
                  className="px-3 py-1 rounded text-xs border border-gray-300 dark:border-[#2a2a5a] hover:bg-gray-100 dark:hover:bg-[#252550] text-gray-700 dark:text-gray-200 disabled:opacity-50"
                >
                  上一页
                </button>
                <button
                  onClick={() => setPage(p => Math.min(totalPages, p + 1))}
                  disabled={page >= totalPages || loading}
                  className="px-3 py-1 rounded text-xs border border-gray-300 dark:border-[#2a2a5a] hover:bg-gray-100 dark:hover:bg-[#252550] text-gray-700 dark:text-gray-200 disabled:opacity-50"
                >
                  下一页
                </button>
              </div>
            </div>
          )}
        </section>
      </div>
    </div>
  )
}
