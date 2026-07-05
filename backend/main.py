"""
智能健康助手 - 主入口
Phase 1: 地基验证
Phase 2: 向量检索验证
Phase 3: 工具层验证
"""

# LangSmith 追踪初始化（必须在所有导入之前）
import os
from dotenv import load_dotenv


# 1. 加载 .env 文件
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))


# 2. 设置 LangSmith 环境变量
os.environ.setdefault("LANGSMITH_TRACING", "true")
os.environ.setdefault("LANGCHAIN_TRACING_V2", "true")
os.environ.setdefault("LANGSMITH_PROJECT", "智能健康助手")
os.environ.setdefault("LANGCHAIN_PROJECT", "智能健康助手")
os.environ.setdefault("LANGSMITH_ENDPOINT", "https://api.smith.langchain.com")
os.environ.setdefault("LANGCHAIN_ENDPOINT", "https://api.smith.langchain.com")


# 3. API Key 从 .env 中读取
#    用户需要在 .env 中添加一行：LANGSMITH_API_KEY=ls__xxxxx
api_key = os.getenv("LANGSMITH_API_KEY") or os.getenv("LANGCHAIN_API_KEY") or ""
if api_key:
    os.environ["LANGSMITH_API_KEY"] = api_key
    os.environ["LANGCHAIN_API_KEY"] = api_key


# 4. 诊断输出（验证环境变量是否生效）
import logging
logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("app.log", encoding="utf-8")
    ]
)
logging.info("=== LangSmith ENV CHECK ===")
logging.info("TRACING: %s", os.environ.get("LANGSMITH_TRACING"))
logging.info("API_KEY: %s...", os.environ.get("LANGSMITH_API_KEY", "")[:10])
logging.info("PROJECT: %s", os.environ.get("LANGSMITH_PROJECT"))
logging.info("ENDPOINT: %s", os.environ.get("LANGSMITH_ENDPOINT"))


import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import asyncio
from database import check_db_connection, check_pgvector, init_db, async_engine, AsyncSessionLocal
from sqlalchemy import text, select


async def verify_tables():
    expected_tables = [
        "users",
        "conversations",
        "messages",
        "knowledge_documents",
        "user_knowledge_config",
        "check_reports",
        "health_reports",
        "consultation_state",
    ]

    async with async_engine.connect() as conn:
        result = await conn.execute(
            text("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'")
        )
        existing = {row[0] for row in result.fetchall()}

    logger.info("\n📦 表检查:")
    all_ok = True
    for table in expected_tables:
        if table in existing:
            logger.info(f"   ✅ {table}")
        else:
            logger.info(f"   ❌ {table} 缺失")
            all_ok = False
    return all_ok


async def verify_models():
    from models import User, Conversation, Message, KnowledgeDocument

    async with AsyncSessionLocal() as session:
        models = [User, Conversation, Message, KnowledgeDocument]
        for model in models:
            try:
                await session.execute(select(model).limit(1))
                logger.info(f"   ✅ {model.__tablename__} 可查询")
            except Exception as e:
                logger.error(f"   ❌ {model.__tablename__} 查询失败: {e}")


async def verify_crud():
    from models import User
    from models.base import generate_uuid

    async with AsyncSessionLocal() as session:
        test_id = generate_uuid()
        test_user = User(
            id=test_id,
            username="test_user_phase1",
            password_hash="test_hash"
        )
        session.add(test_user)
        await session.commit()
        logger.info(f"   ✅ 插入用户: {test_id}")

        result = await session.execute(
            select(User).where(User.id == test_id)
        )
        user = result.scalar_one()
        logger.info(f"   ✅ 查询用户: {user.username}")

        await session.delete(user)
        await session.commit()
        logger.info(f"   ✅ 删除用户")


async def test_vector_search():
    """Phase 2 验证：测试向量检索"""
    import dashscope
    from config import get_settings
    from knowledge.vector_store import search_similar, get_vector_count

    settings = get_settings()
    logger.info("\n" + "=" * 60)
    logger.info("🔍 Phase 2 验证: 向量检索测试")
    logger.info("=" * 60)

    count = await get_vector_count()
    logger.info(f"\n📊 向量表总计: {count} 条记录")

    query = "我头痛，太阳穴跳着疼，伴有恶心"
    logger.info(f"\n🔎 查询: {query}")

    resp = dashscope.TextEmbedding.call(
        model=settings.embedding_model,
        api_key=settings.openai_api_key,
        input=query,
    )
    if resp.status_code != 200:
        logger.error(f"   ❌ Embedding 失败: {resp.code}")
        return

    query_embedding = resp.output["embeddings"][0]["embedding"]
    logger.info(f"   ✅ 向量维度: {len(query_embedding)}")

    results = await search_similar(query_embedding, top_k=3)
    logger.info(f"\n📋 Top-3 检索结果:")
    for i, r in enumerate(results):
        logger.info(f"   {i+1}. [{r['metadata'].get('type', 'N/A')}] 相似度: {r['similarity']:.4f}")
        logger.info(f"      {r['content'][:100]}...")

    logger.info(f"\n{'=' * 60}")
    logger.error("✅ Phase 2 验证通过" if results else "❌ Phase 2 验证失败")
    logger.info(f"{'=' * 60}")


async def test_tools():
    """Phase 3 验证：测试所有工具"""
    from tools.symptom_tools import symptom_search_tool, red_flag_check_tool, disease_info_tool
    from tools.medical_tools import indicator_check_tool, drug_safety_tool, department_info_tool
    from tools.evaluation_tools import completeness_evaluator_tool, pdf_parser_tool
    from tools.document_tools import text_splitter_tool, duplicate_check_tool, quality_scorer_tool
    from tools.population_tools import population_match_tool

    logger.info("\n" + "=" * 60)
    logger.info("🔧 Phase 3 验证: 工具层测试")
    logger.info("=" * 60)

    # 1. 症状检索工具
    logger.info("\n📋 工具1: symptom_search_tool")
    try:
        result = await symptom_search_tool.ainvoke("头痛跳着疼伴有恶心")
        logger.info(f"   ✅ 结果: {result[:150]}...")
    except Exception as e:
        logger.error(f"   ❌ 失败: {e}")

    # 2. 红旗征象检查
    logger.info("\n📋 工具2: red_flag_check_tool")
    try:
        result = await red_flag_check_tool.ainvoke("头痛")
        logger.info(f"   ✅ 结果: {result[:150]}...")
    except Exception as e:
        logger.error(f"   ❌ 失败: {e}")

    # 3. 疾病信息
    logger.info("\n📋 工具3: disease_info_tool")
    try:
        result = await disease_info_tool.ainvoke("头痛")
        logger.info(f"   ✅ 结果: {result[:150]}...")
    except Exception as e:
        logger.error(f"   ❌ 失败: {e}")

    # 4. 指标查询
    logger.info("\n📋 工具4: indicator_check_tool")
    try:
        result = await indicator_check_tool.ainvoke("白细胞")
        logger.info(f"   ✅ 结果: {result[:150]}...")
    except Exception as e:
        logger.error(f"   ❌ 失败: {e}")

    # 5. 药物安全
    logger.info("\n📋 工具5: drug_safety_tool")
    try:
        result = await drug_safety_tool.ainvoke("阿司匹林")
        logger.info(f"   ✅ 结果: {result[:150]}...")
    except Exception as e:
        logger.error(f"   ❌ 失败: {e}")

    # 6. 科室查询
    logger.info("\n📋 工具6: department_info_tool")
    try:
        result = await department_info_tool.ainvoke("头痛")
        logger.info(f"   ✅ 结果: {result[:150]}...")
    except Exception as e:
        logger.error(f"   ❌ 失败: {e}")

    # 7. 完整度评估
    logger.info("\n📋 工具7: completeness_evaluator_tool")
    try:
        test_record = '{"site":"头痛","onset":"3天前","character":"跳痛","severity":"7"}'
        result = completeness_evaluator_tool.invoke(test_record)
        logger.info(f"   ✅ 结果: {result[:150]}...")
    except Exception as e:
        logger.error(f"   ❌ 失败: {e}")

    # 8. PDF解析
    logger.info("\n📋 工具8: pdf_parser_tool")
    try:
        result = pdf_parser_tool.invoke("nonexistent.pdf")
        logger.info(f"   ✅ 结果: {result[:150]}...")
    except Exception as e:
        logger.error(f"   ❌ 失败: {e}")

    # 9. 文档分块
    logger.info("\n📋 工具9: text_splitter_tool")
    try:
        result = text_splitter_tool.invoke({"text": "这是一段测试文本。" * 100})
        logger.info(f"   ✅ 结果: {result[:150]}...")
    except Exception as e:
        logger.error(f"   ❌ 失败: {e}")

    # 10. 重复检测
    logger.info("\n📋 工具10: duplicate_check_tool")
    try:
        result = await duplicate_check_tool.ainvoke("头痛是一种常见的神经系统症状")
        logger.info(f"   ✅ 结果: {result[:150]}...")
    except Exception as e:
        logger.error(f"   ❌ 失败: {e}")

    # 11. 质量评分
    logger.info("\n📋 工具11: quality_scorer_tool")
    try:
        result = quality_scorer_tool.invoke("高血压是一种常见的慢性疾病，主要诊断标准为收缩压≥140mmHg或舒张压≥90mmHg。治疗包括生活方式干预和药物治疗。")
        logger.info(f"   ✅ 结果: {result[:150]}...")
    except Exception as e:
        logger.error(f"   ❌ 失败: {e}")

    # 12. 人群特征
    logger.info("\n📋 工具12: population_match_tool")
    try:
        result = population_match_tool.invoke({"age": 70, "gender": "男", "special_status": "无"})
        logger.info(f"   ✅ 结果: {result[:150]}...")
    except Exception as e:
        logger.error(f"   ❌ 失败: {e}")

    logger.info(f"\n{'=' * 60}")
    logger.info("✅ Phase 3 工具层验证完成")
    logger.info(f"{'=' * 60}")

async def test_triage_agent():
    """Phase 4 验证：测试分诊Agent"""
    from agents.triage_agent import triage

    logger.info("\n" + "=" * 60)
    logger.info("🏥 Phase 4 验证: 分诊Agent测试")
    logger.info("=" * 60)

    test_cases = [
        "我头痛三天了，太阳穴跳着疼",
        "胸口突然剧烈疼痛，喘不上气",
        "最近总是感觉很累，没什么精神",
    ]

    for i, complaint in enumerate(test_cases):
        logger.info(f"\n📋 测试 {i+1}: {complaint}")
        try:
            result = await triage(complaint)
            logger.info(f"   ✅ 紧急等级: {result.urgency}")
            logger.info(f"   ✅ 推荐科室: {result.department}")
            logger.info(f"   ✅ 理由: {result.department_reason}")
            logger.info(f"   ✅ 预问诊问题: {result.pre_questions}")
            if result.red_flags:
                logger.info(f"   ⚠️ 红旗征象: {result.red_flags}")
        except Exception as e:
            logger.error(f"   ❌ 失败: {e}")

    logger.info(f"\n{'=' * 60}")
    logger.info("✅ Phase 4 分诊Agent验证完成")
    logger.info(f"{'=' * 60}")


async def test_consultation_agent():
    """Phase 4 验证：测试问诊Agent — 完整多轮对话直到问诊完成"""
    from agents.consultation_agent import build_consultation_agent

    logger.info("\n" + "=" * 60)
    logger.info("💬 Phase 4 验证: 问诊Agent多轮测试")
    logger.info("=" * 60)

    agent = build_consultation_agent()

    # 模拟完整问诊对话，患者逐步回答
    conversation = [
        "我头痛三天了",
        "太阳穴那边，跳着疼",
        "三天前早上开始的，无缘无故",
        "大概6-7分",
        "没有药物过敏",
        "有点恶心，怕光",
        "以前也有过类似头痛，大概一个月一次",
        "没有在吃药",
    ]

    messages = []

    for i, user_input in enumerate(conversation):
        logger.info(f"\n👤 患者(第{i+1}轮): {user_input}")
        messages.append({"role": "user", "content": user_input})
        try:
            result = await agent.ainvoke({"messages": messages})
            ai_messages = [m for m in result["messages"] if m.type == "ai"]
            if ai_messages:
                response = ai_messages[-1].content
                logger.info(f"🤖 医生: {response[:300]}...")
                messages = result["messages"]

                if "【问诊完成】" in response:
                    logger.info(f"\n✅ 问诊完整度达标，问诊完成!")
                    break
        except Exception as e:
            logger.error(f"   ❌ 第{i+1}轮失败: {e}")
            break

    logger.info(f"\n{'=' * 60}")
    logger.info("✅ Phase 4 问诊Agent验证完成")
    logger.info(f"{'=' * 60}")


async def test_report_analysis_agent():
    """Phase 4 验证：测试报告分析Agent"""
    from agents.report_analysis_agent import analyze_report

    logger.info("\n" + "=" * 60)
    logger.info("📄 Phase 4 验证: 报告分析Agent测试")
    logger.info("=" * 60)

    # 模拟一份血常规报告
    sample_report = """
    某某医院检验报告单

    姓名：张三  性别：男  年龄：35

    项目名称          结果        参考范围        单位
    白细胞(WBC)       12.5        4.0-10.0       10⁹/L
    中性粒细胞        9.2         1.8-6.3        10⁹/L
    淋巴细胞          2.1         1.1-3.2        10⁹/L
    血红蛋白(Hb)      145         120-160        g/L
    血小板(PLT)       210         100-300        10⁹/L
    C反应蛋白(CRP)    28.6        <5             mg/L
    """

    logger.info(f"\n📋 模拟报告:\n{sample_report}")

    try:
        result = await analyze_report(sample_report)
        logger.info(f"\n🤖 分析结果:\n{result}")
    except Exception as e:
        logger.error(f"   ❌ 失败: {e}")

    logger.info(f"\n{'=' * 60}")
    logger.info("✅ Phase 4 报告分析Agent验证完成")
    logger.info(f"{'=' * 60}")


async def test_phase5_agents():
    """Phase 5 验证：Agent 4-7 串联测试"""
    from agents.knowledge_retrieval_agent import retrieve_and_analyze
    from agents.diagnosis_agent import diagnose
    from agents.risk_warning_agent import assess_risk
    from agents.report_generation_agent import generate_report
    from agents.triage_agent import triage

    logger.info("\n" + "=" * 60)
    logger.info("🧪 Phase 5 验证: Agent 4-7 串联测试")
    logger.info("=" * 60)

    # 模拟上游数据
    chief_complaint = "头痛三天，太阳穴跳着疼，有点恶心"

    consultation_record = """
    - 主诉：头痛三天
    - 部位(site)：太阳穴，单侧
    - 起病时间(onset)：三天前早上
    - 性质(character)：跳着疼（搏动性）
    - 严重程度(severity)：6-7分
    - 伴随症状(associated)：恶心、怕光
    - 既往史(past_history)：每月发作一次类似头痛
    - 用药史(medication)：无
    - 过敏史(allergy)：无
    """

    report_analysis = """
    白细胞：12.5(偏高)，中性粒细胞：9.2(偏高)，CRP：28.6(偏高)
    """

    # Agent 4: 知识检索
    logger.info("\n📚 Agent 4: 知识检索")
    rag_result = await retrieve_and_analyze(consultation_record, report_analysis)
    logger.info(f"   结果: {rag_result[:200]}...")

    # Agent 5: 诊断建议
    logger.info("\n🩺 Agent 5: 诊断建议")
    diagnosis = await diagnose(consultation_record, report_analysis, rag_result)
    logger.info(f"   结果: {diagnosis[:200]}...")

    # Agent 6: 风险预警
    logger.info("\n⚠️ Agent 6: 风险预警")
    risk = await assess_risk(consultation_record, report_analysis, diagnosis)
    logger.info(f"   结果: {risk[:200]}...")

    # Agent 7: 报告生成
    logger.info("\n📄 Agent 7: 报告生成")
    triage_result = await triage(chief_complaint)
    triage_text = f"紧急等级：{triage_result.urgency}，推荐科室：{triage_result.department}"
    report = await generate_report(
        chief_complaint=chief_complaint,
        triage_result=triage_text,
        consultation_record=consultation_record,
        report_analysis=report_analysis,
        rag_reference=rag_result,
        diagnosis=diagnosis,
        risk_warning=risk,
    )
    logger.info(f"   结果: {report[:300]}...")

    logger.info(f"\n{'=' * 60}")
    logger.info("✅ Phase 5 Agent 4-7 串联验证完成")
    logger.info(f"{'=' * 60}")


async def test_phase6_workflow():
    """Phase 6 验证：LangGraph 工作流端到端测试"""
    from graph.workflow import run_workflow

    logger.info("\n" + "=" * 60)
    logger.info("🔄 Phase 6 验证: LangGraph 工作流测试")
    logger.info("=" * 60)

    logger.info("\n🚀 启动工作流: 患者主诉「头痛三天，太阳穴跳着疼」")

    try:
        result = await run_workflow("头痛三天，太阳穴跳着疼")

        logger.info(f"\n📋 分诊结果: {result.get('triage_urgency', 'N/A')} → {result.get('triage_department', 'N/A')}")
        logger.info(f"\n📋 问诊阶段: {result.get('consultation_phase', 'N/A')}")
        logger.info(f"\n📋 最终报告:\n{result.get('final_report', 'N/A')[:500]}...")

    except Exception as e:
        logger.error(f"   ❌ 工作流失败: {e}")
        import traceback
        traceback.print_exc()

    logger.info(f"\n{'=' * 60}")
    logger.info("✅ Phase 6 工作流验证完成")
    logger.info(f"{'=' * 60}")
async def test_phase7_middleware():
    """Phase 7 验证：中间件测试"""
    from middleware.health_callback import HealthAgentCallback

    logger.info("\n" + "=" * 60)
    logger.info("🎛️ Phase 7 验证: 中间件测试")
    logger.info("=" * 60)

    callback = HealthAgentCallback(verbose=True)

    # 测试脱敏
    test_texts = [
        "我叫张三，身份证号123456789012345678",
        "手机号13812345678，地址：北京市朝阳区某某街道100号",
    ]
    logger.info("\n🔒 脱敏测试:")
    for text in test_texts:
        result = callback._desensitize(text)
        logger.info(f"   原文: {text}")
        logger.info(f"   脱敏: {result}")

    # 测试问诊轮数
    logger.info(f"\n🔄 问诊轮数检查:")
    for i in range(12):
        callback.consultation_round += 1
        if callback.is_consultation_timeout():
            logger.info(f"   ⚠️ 第{i+1}轮: 超时触发")
            break

    # 测试异常重试
    logger.error(f"\n⚠️ 异常重试测试:")
    for i in range(5):
        callback.error_count += 1
        logger.error(f"   第{i+1}次异常: {'重试' if callback.should_retry() else '停止重试'}")

    callback.print_stats()

    logger.info(f"\n{'=' * 60}")
    logger.info("✅ Phase 7 中间件验证完成")
    logger.info(f"{'=' * 60}")


async def _ensure_knowledge_documents_columns():
    """启动时自动补齐 knowledge_documents / medical_knowledge_vectors 表缺失的列"""
    try:
        async with async_engine.connect() as conn:
            alter_sqls = [
                "ALTER TABLE knowledge_documents ADD COLUMN IF NOT EXISTS title VARCHAR(500)",
                "ALTER TABLE knowledge_documents ADD COLUMN IF NOT EXISTS source VARCHAR(200) DEFAULT '种子数据'",
                "ALTER TABLE knowledge_documents ADD COLUMN IF NOT EXISTS status VARCHAR(50) DEFAULT 'active'",
                "ALTER TABLE knowledge_documents ADD COLUMN IF NOT EXISTS quality_score DOUBLE PRECISION",
                "ALTER TABLE knowledge_documents ADD COLUMN IF NOT EXISTS chunk_count INTEGER DEFAULT 0",
                "ALTER TABLE knowledge_documents ADD COLUMN IF NOT EXISTS user_id VARCHAR(255)",
                "ALTER TABLE knowledge_documents ADD COLUMN IF NOT EXISTS file_type VARCHAR(50)",
                "ALTER TABLE knowledge_documents ADD COLUMN IF NOT EXISTS file_size INTEGER",
                "ALTER TABLE knowledge_documents ADD COLUMN IF NOT EXISTS file_path VARCHAR(1000)",
                "ALTER TABLE knowledge_documents ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT now()",
                "ALTER TABLE medical_knowledge_vectors ADD COLUMN IF NOT EXISTS chunk_index INTEGER DEFAULT 0",
                "ALTER TABLE medical_knowledge_vectors ADD COLUMN IF NOT EXISTS extra_metadata JSONB",
            ]
            for col_sql in alter_sqls:
                await conn.execute(text(col_sql))
            await conn.commit()
        logger.info("[Knowledge] 知识库字段检查完成")
    except Exception as e:
        logger.error(f"[Knowledge] 知识库字段检查异常: {e}")


def start_api():
    """启动 FastAPI 服务"""
    import uvicorn
    from fastapi import FastAPI
    from fastapi.middleware.cors import CORSMiddleware
    from contextlib import asynccontextmanager
    from api.chat import router as chat_router
    from api.upload import router as upload_router
    from api.report import router as report_router
    from api.retrieval import router as retrieval_router
    from api.history import router as history_router
    from api.tts import router as tts_router
    from api.knowledge import router as knowledge_router
    from graph.workflow import init_checkpointer, close_checkpointer
    
    logger.info("\n[OCR] OCR 服务说明:")
    logger.info("   图片文字识别优先级:")
    logger.info("   1. MinerU 在线 API（免登录，优先使用）")
    logger.info("   2. Tesseract OCR（需本地安装）")
    logger.info("   3. OCR.space API（备用方案）")

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        await init_checkpointer()
        await _ensure_knowledge_documents_columns()
        yield
        await close_checkpointer()
    
    app = FastAPI(title="智能健康助手 API", lifespan=lifespan)

    allowed_origins_str = os.getenv("ALLOWED_ORIGINS", "http://localhost:5173,http://localhost:5174")
    allowed_origins = [o.strip() for o in allowed_origins_str.split(",") if o.strip()]

    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "OPTIONS", "DELETE"],
        allow_headers=["*"],
    )

    app.include_router(chat_router)
    app.include_router(upload_router)
    app.include_router(report_router)
    app.include_router(retrieval_router)
    app.include_router(history_router)
    app.include_router(tts_router)
    app.include_router(knowledge_router)

    @app.get("/")
    async def root():
        return {"status": "running", "service": "智能健康助手"}

    uvicorn.run(app, host="0.0.0.0", port=8000)
async def main():
    logger.info("=" * 60)
    logger.info("[Phase 1] 地基验证")
    logger.info("=" * 60)

    from config import get_settings
    settings = get_settings()
    logger.info("\n[配置]:")
    logger.info(f"   数据库: {settings.database_url}")
    logger.info(f"   LLM 模型: {settings.llm_model}")
    logger.info(f"   Embedding: {settings.embedding_model}")

    logger.info("\n[初始化数据库...]")
    try:
        init_db()
        logger.info("   [OK] 建表完成")
    except Exception as e:
        logger.error(f"   [FAIL] 建表失败: {e}")
        sys.exit(1)

    logger.info("\n[测试连接...]")
    if not await check_db_connection():
        logger.info("   [FAIL] 请检查 PostgreSQL 是否运行")
        sys.exit(1)
    logger.info("   [OK] 连接成功")

    logger.info("\n[检查 pgvector...]")
    if not await check_pgvector():
        logger.info("   [FAIL] 请执行: CREATE EXTENSION vector;")
        sys.exit(1)
    logger.info("   [OK] pgvector 就绪")

    if not await verify_tables():
        sys.exit(1)

    logger.info("\n[验证模型...]")
    await verify_models()

    logger.info("\n[验证 CRUD...]")
    try:
        await verify_crud()
    except Exception as e:
        logger.error(f"   [FAIL] CRUD 失败: {e}")
        sys.exit(1)

    logger.info(f"\n{'=' * 60}")
    logger.info("[OK] Phase 1 地基完成，所有验证通过")
    logger.info(f"{'=' * 60}")

    # Phase 2 验证
    await test_vector_search()

    # Phase 3 验证
    await test_tools()
    # Phase 4 验证
    await test_triage_agent()
    # Phase 4 续：问诊Agent
    await test_consultation_agent()
    # Phase 4 续：报告分析Agent
    await test_report_analysis_agent()
    # Phase 5 验证
    await test_phase5_agents()
    # Phase 6 验证
    await test_phase6_workflow()
    # Phase 7 验证
    await test_phase7_middleware()
async def test_chat_flow():
    """一问一答流程测试"""
    from graph.workflow import triage_node, consultation_node

    # 初始状态
    state = {
        "user_id": "test",
        "session_id": "test",
        "messages": [],
        "chief_complaint": "头痛三天",
        "triage_urgency": "",
        "triage_department": "",
        "triage_summary": "",
        "consultation_phase": "asking",
        "consultation_record": "",
        "completeness_score": 0,
        "pending_reports": [],
        "analyzed_reports": [],
        "report_analysis": "",
        "rag_result": "",
        "diagnosis": "",
        "risk_warning": "",
        "final_report": "",
        "next_step": "triage",
        "error": None,
    }

    logger.info("=" * 60)
    logger.info("[一问一答流程测试]")
    logger.info("=" * 60)

    # 第1步：分诊
    logger.info("\n[分诊...]")
    result = await triage_node(state)
    state.update(result)
    logger.info(f"   紧急: {result['triage_urgency']}, 科室: {result['triage_department']}")

    # 第2步：第1轮问诊
    logger.info("\n[第1轮问诊——用户: 太阳穴跳着疼]")
    state["messages"].append({"role": "user", "content": "太阳穴跳着疼"})
    result = await consultation_node(state)
    state.update(result)
    ai_msgs = [m for m in result["messages"] if hasattr(m, 'type') and m.type == "ai"]
    if ai_msgs:
        logger.info(f"   医生: {ai_msgs[-1].content[:200]}...")
    else:
        logger.info("   [FAIL] 没有AI回复")
        # 打印所有消息看看结构
        for m in result["messages"]:
            logger.info(f"      msg: type={type(m).__name__}, content={str(m)[:100]}")
        return

    # 第3步：第2轮问诊
    logger.info("\n[第2轮问诊——用户: 6-7分，没有过敏]")
    state["messages"].append({"role": "user", "content": "6-7分，没有过敏"})
    result = await consultation_node(state)
    state.update(result)
    ai_msgs = [m for m in result["messages"] if hasattr(m, 'type') and m.type == "ai"]
    if ai_msgs:
        logger.info(f"   医生: {ai_msgs[-1].content[:200]}...")
    else:
        logger.info("   [FAIL] 没有AI回复")

    logger.info(f"\n[OK] 测试完成，共 {state.get('completeness_score', 0)} 轮")
if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "api":
        start_api()
    else:
        asyncio.run(main())
    # asyncio.run(test_chat_flow())