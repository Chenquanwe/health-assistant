# 智能健康助手 (AI Health Assistant)

基于大语言模型与多智能体协同的智能医疗问诊系统

---

## 项目简介

智能健康助手是一个面向在线医疗问诊、健康咨询、体检报告解读和医学知识管理场景的 AI 系统，通过模拟全科医生的问诊流程，帮助用户进行初步健康咨询和症状评估。系统融合了多轮问诊采集症状、知识库检索增强回答、语音输入/播报、自动生成健康报告等核心功能，旨在帮助用户快速获取初步健康评估，减轻医生咨询压力；同时提供可追溯的 AI 思考过程，增强用户信任感；支持用户自定义医学知识库，提升回答的专业性和针对性。技术上采用 ReAct Agent 模式实现智能决策、RAG 检索增强提升回答准确性、WebSocket 实时流式对话保证流畅交互、Docker 容器化部署简化运维。

### 核心能力

- **多轮问诊**：采用 ReAct Agent 模式，基于 SOCRATES 医学框架逐项采集部位、时间、性质、严重程度等信息，自动生成结构化问诊记录
- **知识库管理**：支持上传 PDF、DOCX、MD、TXT、PNG、JPG 等格式的医学文档，自动分块、生成 Embedding 并存入 pgvector 向量数据库，问诊时 AI 可检索引用；用户可在前端上传、删除、查看医学文档
- **语音交互**：前端按住麦克风说话，后端通过 DashScope ASR 转为文字；AI 回复可通过 TTS 流式语音播报，支持中断和逐句播放
- **健康报告**：基于完整对话历史自动生成包含基本信息、问诊摘要、危险信号评估、鉴别诊断、就诊建议等 7 段式 Markdown 报告，支持预览和导出 Word/PDF
- **思考过程展示**：可选择开启"思考详情"，在聊天界面实时查看 AI 正在调用什么工具、检索到了哪些知识

---

## 系统架构

```
┌─────────────────────────────────────────────────────────────────┐
│                         前端 (React)                           │
│         ChatView | KnowledgeManager | HistoryPage              │
└─────────────────────────┬───────────────────────────────────────┘
                          │ WebSocket / HTTP
┌─────────────────────────▼───────────────────────────────────────┐
│                      后端 (FastAPI)                             │
│      API Routes | WebSocket Handler | Session Management       │
└─────────────────────────┬───────────────────────────────────────┘
                          │ Agent Tools
┌─────────────────────────▼───────────────────────────────────────┐
│                      工具层 (LangChain)                         │
│   SymptomTools | KnowledgeTools | EvaluationTools | TTS        │
└─────────────────────────┬───────────────────────────────────────┘
                          │ Vector Search
┌─────────────────────────▼───────────────────────────────────────┐
│                   知识库 (pgvector)                            │
│           MedicalKnowledgeVectors | KnowledgeDocuments         │
└─────────────────────────┬───────────────────────────────────────┘
                          │ SQL
┌─────────────────────────▼───────────────────────────────────────┐
│                    数据库 (PostgreSQL)                          │
│              Conversations | Reports | Users | Knowledge        │
└─────────────────────────────────────────────────────────────────┘
```

### 架构分层说明

| 层级 | 职责 |
|------|------|
| **前端** | 用户界面、聊天交互、语音交互、文档管理 |
| **后端** | API 路由、WebSocket 实时通信、会话管理 |
| **工具层** | 症状检索、知识库查询、完整度评估、语音合成 |
| **知识库** | 向量存储、语义检索、文档管理 |
| **数据库** | 结构化数据存储、会话历史、报告数据 |

---

## 技术栈

| 类别 | 技术 | 版本/说明 |
|------|------|-----------|
| **前端** | React | 19.2.5 |
| | Vite | 8.0.10 |
| | Tailwind CSS | 4.2.4 |
| | react-markdown | 10.1.0 |
| **后端框架** | FastAPI | 0.136.1 |
| | Uvicorn | 0.46.0 |
| **AI 编排** | LangChain | 1.2.17 |
| | LangGraph | 1.1.10 |
| **LLM 模型** | DashScope (qwen-plus) | 兼容 OpenAI 接口 |
| **Embedding** | DashScope (text-embedding-v4) | 1024 维向量 |
| **语音服务** | DashScope TTS | 流式语音合成 |
| **数据库** | PostgreSQL | 16.x + pgvector 0.4.2 |
| **ORM** | SQLAlchemy | 2.0.49 (async) |
| **容器化** | Docker / Docker Compose | 3.8+ |
| **监控追踪** | LangSmith | 0.8.0 |
| **报告导出** | python-docx 1.2.0 + Pillow 12.2.0 | Word/PDF 导出 |

---

## 快速开始

### 前置要求

- **Docker 部署**：需要安装 Docker Desktop（或 Docker Engine + Docker Compose）
- **本地手动部署**：需要安装 Python 3.11+、Node.js 18+、PostgreSQL 16（并启用 pgvector 扩展）
- **API Key**：提前准备好 LLM 服务的 API Key（如阿里云 DashScope，或任何兼容 OpenAI 接口的服务）

### 方式一：Docker 部署（推荐）

```bash
# 1. 克隆项目
git clone <repository-url>
cd health-assistant

# 2. 配置环境变量
cp backend/.env.example backend/.env

# 编辑 backend/.env，填写以下必填项：
#   DASHSCOPE_API_KEY=你的阿里云API密钥（从 `https://dashscope.aliyun.com` 获取）
#   OPENAI_API_KEY=与 DASHSCOPE_API_KEY 相同
#   OPENAI_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
#   LLM_MODEL=qwen-plus
#
# 说明：本项目兼容 OpenAI 接口，如果你不想用阿里云 DashScope，
# 只需将 OPENAI_BASE_URL 改为其他服务地址（如 DeepSeek、One API），
# 并填写对应的 OPENAI_API_KEY 和模型名称即可。
#
# 可选配置（不填也不影响核心功能）：
#   LANGSMITH_API_KEY=你的LangSmith密钥（追踪 Agent 执行过程）
#   OCR_SPACE_API_KEY=你的OCR.space密钥（备用图片识别）
```

> ⚠️ 必须修改 .env 中的 API Key，否则服务无法正常使用

```bash
# 3. 启动后端服务（含数据库）
docker-compose up -d

# 4. 启动前端
cd frontend
npm install
npm run dev

# 5. 访问
# 后端 API: http://localhost:8000
# 前端页面: http://localhost:5173
```

**注意**：首次启动时，数据库会自动初始化，可能需要等待 30 秒。

### 方式二：手动部署

#### 后端

```bash
cd backend

# 安装依赖
pip install -r requirements.txt

# 配置 PostgreSQL + pgvector
# 1. 创建数据库: health_agent
# 2. 安装 pgvector 扩展

cp .env.example .env
# 编辑 .env，填写必填项（同上，参考 Docker 部署中的详细说明）

# 启动服务
python main.py api
```

#### 前端

```bash
cd frontend

# 安装依赖
npm install

# 启动开发服务器
npm run dev
```

---

## 项目目录结构

```
智能健康助手/
├── backend/                          # 后端代码
│   ├── api/                          # HTTP/WebSocket API
│   │   ├── chat.py                   # 聊天 WebSocket
│   │   ├── knowledge.py              # 知识库 API
│   │   ├── tts.py                    # TTS API
│   │   ├── upload.py                 # 文件上传 API
│   │   ├── report.py                 # 报告 API
│   │   ├── history.py                # 历史记录 API
│   │   └── retrieval.py              # 检索 API
│   ├── agents/                       # 多智能体
│   │   ├── consultation_agent.py     # 问诊 Agent
│   │   ├── diagnosis_agent.py        # 诊断 Agent
│   │   ├── report_generation_agent.py # 报告生成 Agent
│   │   └── ...
│   ├── tools/                        # 工具集
│   │   ├── symptom_tools.py          # 症状工具
│   │   ├── knowledge_tools.py        # 知识库工具
│   │   └── evaluation_tools.py       # 评估工具
│   ├── knowledge/                    # 知识库模块
│   │   ├── vector_store.py           # 向量存储
│   │   ├── hybrid_retriever.py       # 混合检索
│   │   └── seed_data/                # 种子医学知识
│   ├── models/                       # SQLAlchemy 模型
│   ├── services/                     # 服务层
│   │   └── voice_service.py          # 语音服务
│   ├── graph/                        # LangGraph 工作流
│   ├── utils/                        # 工具函数
│   ├── scripts/                      # 迁移脚本
│   ├── middleware/                   # 中间件
│   ├── uploads/                      # 用户上传文件（运行时生成）
│   ├── main.py                       # 应用入口
│   ├── config.py                     # 配置管理
│   ├── database.py                   # 数据库连接
│   ├── requirements.txt              # Python 依赖
│   ├── Dockerfile                    # Docker 构建
│   └── .env.example                  # 环境变量模板
├── frontend/                         # 前端代码
│   ├── src/
│   │   ├── App.jsx                   # 主应用组件
│   │   ├── main.jsx                  # React 入口
│   │   ├── components/               # 组件
│   │   │   ├── KnowledgeManager.jsx  # 知识库管理
│   │   │   └── ...
│   │   └── assets/                   # 静态资源
│   ├── public/                       # 公共文件
│   ├── package.json                  # 前端依赖
│   ├── vite.config.js                # Vite 配置
│   └── .gitignore                    # 前端忽略规则
├── test_data/                        # 测试数据（图片）
├── docker-compose.yml                # Docker Compose 配置
├── .gitignore                        # 根目录忽略规则
└── README.md                         # 项目说明
```

---

## 当前已知问题

1. **LangGraph 完整工作流未启用**：当前使用简单 ReAct 模式，完整多智能体工作流待集成
2. **硬编码医学知识**：部分医学知识硬编码在 Prompt 中，需迁移到知识库
3. **前端缺少路由和状态管理**：当前使用简单状态管理，缺少 React Router 和状态管理库
4. **报告导出功能**：已支持预览和下载，但导出格式（PDF/Word）的排版仍有优化空间

---

## 未来改进方向

- [ ] **历史消息裁剪**：限制上下文长度，提升首 token 响应速度
- [ ] **Embedding 缓存**：对高频查询结果进行缓存，减少 API 调用
- [ ] **前端工程化**：引入 React Router、状态管理库、代码分割
- [ ] **数据库迁移工具**：使用 Alembic 管理数据库 schema 变更
- [ ] **单元测试**：为核心模块添加测试覆盖
- [ ] **多模型支持**：支持切换不同的 LLM 和 Embedding 模型
- [ ] **用户认证**：添加用户注册/登录功能
- [ ] **报告模板定制**：支持自定义报告模板和导出格式
- [ ] **移动端适配**：优化移动端界面体验
- [ ] **性能监控**：集成 Prometheus + Grafana 监控

---

## 许可证

MIT License

---

## 贡献

欢迎提交 Issue 和 Pull Request！

---

## ⚠️ 重要声明

本助手提供的所有健康建议均由 AI 自动生成，**仅供参考，不构成医疗诊断或处方**。如有身体不适，请及时前往正规医疗机构就诊，以医生面诊意见为准。本项目仅用于个人学习、技术交流和非商业用途。