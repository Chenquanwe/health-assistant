import { useState, useCallback } from 'react'

const API_BASE = 'http://localhost:8000'

// 文件上传组件
export function FileUploader({ onUploadSuccess, onUploadError }) {
  const [isDragging, setIsDragging] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [uploadedFiles, setUploadedFiles] = useState([])
  const [currentUpload, setCurrentUpload] = useState(null)

  const handleDragOver = useCallback((e) => {
    e.preventDefault()
    setIsDragging(true)
  }, [])

  const handleDragLeave = useCallback((e) => {
    e.preventDefault()
    setIsDragging(false)
  }, [])

  const handleDrop = useCallback((e) => {
    e.preventDefault()
    setIsDragging(false)
    const files = Array.from(e.dataTransfer.files)
    if (files.length > 0) {
      uploadFile(files[0])
    }
  }, [])

  const handleFileSelect = useCallback((e) => {
    const files = Array.from(e.target.files)
    if (files.length > 0) {
      uploadFile(files[0])
    }
  }, [])

  const uploadFile = async (file) => {
    // 检查文件类型
    const allowedTypes = ['application/pdf', 'image/png', 'image/jpeg', 'image/jpg']
    if (!allowedTypes.includes(file.type)) {
      onUploadError?.('不支持的文件类型，请上传 PDF、PNG 或 JPG 图片')
      return
    }

    // 检查文件大小（最大 10MB）
    if (file.size > 10 * 1024 * 1024) {
      onUploadError?.('文件过大，请上传小于 10MB 的文件')
      return
    }

    setUploading(true)
    setCurrentUpload(file.name)

    try {
      const formData = new FormData()
      formData.append('file', file)

      const response = await fetch(`${API_BASE}/api/upload`, {
        method: 'POST',
        body: formData,
      })

      const data = await response.json()

      if (data.success) {
        const fileInfo = {
          file_id: data.file_id,
          file_name: data.file_name,
          file_type: data.file_type,
          extracted_text: data.extracted_text,
          upload_time: new Date().toISOString(),
        }
        
        setUploadedFiles(prev => [...prev, fileInfo])
        onUploadSuccess?.(fileInfo)
        
        // 显示提取的文本
        if (data.extracted_text) {
          console.log('提取的文本:', data.extracted_text)
        }
      } else {
        onUploadError?.(data.detail || '上传失败')
      }
    } catch (error) {
      console.error('上传错误:', error)
      onUploadError?.('上传失败，请检查网络连接')
    } finally {
      setUploading(false)
      setCurrentUpload(null)
    }
  }

  const removeFile = (fileId) => {
    setUploadedFiles(prev => prev.filter(f => f.file_id !== fileId))
  }

  return (
    <div className="space-y-4">
      {/* 拖拽上传区域 */}
      <div
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
        className={`border-2 border-dashed rounded-xl p-8 text-center transition-colors ${
          isDragging
            ? 'border-blue-500 bg-blue-50'
            : 'border-gray-300 hover:border-blue-400'
        }`}
      >
        <div className="flex flex-col items-center gap-3">
          <div className="text-4xl">{uploading ? '⏳' : '📄'}</div>
          <div>
            <p className="font-medium text-gray-700">
              {uploading ? `正在上传: ${currentUpload}` : '拖拽文件到此处上传'}
            </p>
            <p className="text-sm text-gray-500 mt-1">
              支持 PDF、PNG、JPG 格式，最大 10MB
            </p>
          </div>
          <label className="cursor-pointer">
            <input
              type="file"
              accept=".pdf,.png,.jpg,.jpeg"
              onChange={handleFileSelect}
              className="hidden"
              disabled={uploading}
            />
            <span className="inline-flex items-center gap-2 px-4 py-2 bg-blue-500 text-white rounded-lg hover:bg-blue-600 transition-colors disabled:opacity-50">
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12" />
              </svg>
              {uploading ? '上传中...' : '选择文件'}
            </span>
          </label>
        </div>
      </div>

      {/* 已上传文件列表 */}
      {uploadedFiles.length > 0 && (
        <div className="space-y-2">
          <h4 className="text-sm font-medium text-gray-700">已上传文件：</h4>
          {uploadedFiles.map((file) => (
            <div
              key={file.file_id}
              className="flex items-center justify-between p-3 bg-gray-50 rounded-lg"
            >
              <div className="flex items-center gap-3">
                <span className="text-xl">
                  {file.file_type === 'pdf' ? '📑' : '🖼️'}
                </span>
                <div>
                  <p className="text-sm font-medium text-gray-700">{file.file_name}</p>
                  <p className="text-xs text-gray-500">
                    {file.file_type.toUpperCase()} · {formatFileSize(file.file_size || 0)}
                  </p>
                </div>
              </div>
              <button
                onClick={() => removeFile(file.file_id)}
                className="p-1 text-gray-400 hover:text-red-500 transition-colors"
                title="删除"
              >
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

// 文件大小格式化
function formatFileSize(bytes) {
  if (bytes === 0) return '未知大小'
  const k = 1024
  const sizes = ['B', 'KB', 'MB', 'GB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i]
}

// 分析报告组件
export function ReportAnalyzer({ fileId, onAnalysisComplete }) {
  const [analyzing, setAnalyzing] = useState(false)
  const [analysisResult, setAnalysisResult] = useState(null)
  const [error, setError] = useState(null)

  const analyzeReport = async () => {
    if (!fileId) return

    setAnalyzing(true)
    setError(null)

    try {
      const response = await fetch(`${API_BASE}/api/upload/analyze?file_id=${fileId}`, {
        method: 'POST',
      })

      const data = await response.json()

      if (data.success) {
        setAnalysisResult(data.analysis)
        onAnalysisComplete?.(data.analysis)
      } else {
        setError(data.message || '分析失败')
      }
    } catch (error) {
      console.error('分析错误:', error)
      setError('分析失败，请重试')
    } finally {
      setAnalyzing(false)
    }
  }

  if (analyzing) {
    return (
      <div className="flex items-center gap-3 p-4 bg-blue-50 rounded-lg">
        <div className="flex gap-1">
          <div className="w-2 h-2 bg-blue-500 rounded-full animate-bounce" style={{animationDelay:'0ms'}}></div>
          <div className="w-2 h-2 bg-blue-500 rounded-full animate-bounce" style={{animationDelay:'150ms'}}></div>
          <div className="w-2 h-2 bg-blue-500 rounded-full animate-bounce" style={{animationDelay:'300ms'}}></div>
        </div>
        <span className="text-sm text-blue-600">正在分析报告内容...</span>
      </div>
    )
  }

  if (error) {
    return (
      <div className="p-4 bg-red-50 border border-red-200 rounded-lg">
        <p className="text-sm text-red-600">{error}</p>
        <button
          onClick={analyzeReport}
          className="mt-2 text-sm text-blue-500 hover:underline"
        >
          重试
        </button>
      </div>
    )
  }

  if (analysisResult) {
    return (
      <div className="space-y-4">
        {/* 异常指标 */}
        {analysisResult.indicators && analysisResult.indicators.length > 0 && (
          <div className="bg-white border rounded-lg p-4">
            <h4 className="font-medium text-gray-700 mb-3">📊 检查指标</h4>
            <div className="space-y-2">
              {analysisResult.indicators.map((indicator, idx) => (
                <div
                  key={idx}
                  className={`p-3 rounded-lg ${
                    indicator.status === 'normal'
                      ? 'bg-green-50 border border-green-200'
                      : 'bg-orange-50 border border-orange-200'
                  }`}
                >
                  <div className="flex justify-between items-start">
                    <div>
                      <p className="font-medium text-gray-700">{indicator.name}</p>
                      <p className="text-sm text-gray-500">{indicator.value}</p>
                    </div>
                    <span className={`text-xs px-2 py-1 rounded-full ${
                      indicator.status === 'normal'
                        ? 'bg-green-100 text-green-700'
                        : 'bg-orange-100 text-orange-700'
                    }`}>
                      {indicator.status === 'normal' ? '正常' : '异常'}
                    </span>
                  </div>
                  {indicator.reference && (
                    <p className="text-xs text-gray-400 mt-1">参考值: {indicator.reference}</p>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}

        {/* 总结 */}
        {analysisResult.summary && (
          <div className="bg-gray-50 border rounded-lg p-4">
            <h4 className="font-medium text-gray-700 mb-2">📝 总结</h4>
            <p className="text-sm text-gray-600">{analysisResult.summary}</p>
          </div>
        )}

        {/* 需要关注的项 */}
        {analysisResult.alerts && analysisResult.alerts.length > 0 && (
          <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-4">
            <h4 className="font-medium text-yellow-700 mb-2">⚠️ 需要关注</h4>
            <ul className="space-y-1">
              {analysisResult.alerts.map((alert, idx) => (
                <li key={idx} className="text-sm text-yellow-600">• {alert}</li>
              ))}
            </ul>
          </div>
        )}
      </div>
    )
  }

  // 默认状态
  return (
    <div className="text-center py-4">
      <button
        onClick={analyzeReport}
        disabled={!fileId}
        className="px-4 py-2 bg-green-500 text-white rounded-lg hover:bg-green-600 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
      >
        🔍 分析报告
      </button>
      <p className="text-xs text-gray-500 mt-2">
        点击按钮使用 AI 分析报告中的异常指标
      </p>
    </div>
  )
}

// 完整的上传+分析组件
export function ReportUploader() {
  const [uploadedFile, setUploadedFile] = useState(null)
  const [error, setError] = useState(null)

  const handleUploadSuccess = (fileInfo) => {
    setUploadedFile(fileInfo)
    setError(null)
  }

  const handleUploadError = (errorMsg) => {
    setError(errorMsg)
  }

  return (
    <div className="space-y-4">
      <FileUploader
        onUploadSuccess={handleUploadSuccess}
        onUploadError={handleUploadError}
      />

      {error && (
        <div className="p-3 bg-red-50 border border-red-200 rounded-lg">
          <p className="text-sm text-red-600">{error}</p>
        </div>
      )}

      {uploadedFile && (
        <div className="border-t pt-4">
          <h4 className="text-sm font-medium text-gray-700 mb-3">
            📋 报告分析
          </h4>
          <ReportAnalyzer
            fileId={uploadedFile.file_id}
          />
        </div>
      )}
    </div>
  )
}

export default ReportUploader
