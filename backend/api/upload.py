"""
报告上传 API
支持 PDF 和图片（PNG/JPG/JPEG）的上传、解析和 OCR
"""
import os
import logging
logger = logging.getLogger(__name__)
import uuid
import json
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, UploadFile, File, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/api/upload", tags=["上传"])

# 上传文件存储目录
UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)

# 报告存储目录
REPORT_DIR = UPLOAD_DIR / "reports"
REPORT_DIR.mkdir(exist_ok=True)


class UploadResponse(BaseModel):
    """上传响应"""
    success: bool
    file_id: str
    file_name: str
    file_type: str
    file_size: int
    extracted_text: Optional[str] = None
    message: str


class AnalysisResponse(BaseModel):
    """分析响应"""
    success: bool
    file_id: str
    analysis: dict
    message: str


@router.post("", response_model=UploadResponse)
async def upload_report(file: UploadFile = File(...)):
    """
    上传检查报告文件（PDF 或图片）
    
    - 支持格式: PDF, PNG, JPG, JPEG
    - 自动解析文本内容
    - 返回提取的文字内容
    """
    # 检查文件类型
    allowed_types = {
        "application/pdf": "pdf",
        "image/png": "png",
        "image/jpeg": "jpg",
        "image/jpg": "jpg",
    }
    
    content_type = file.content_type
    if content_type not in allowed_types:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的文件类型: {content_type}。支持的类型: PDF, PNG, JPG, JPEG"
        )
    
    file_type = allowed_types[content_type]
    
    # 读取文件内容
    contents = await file.read()
    file_size = len(contents)
    
    # 生成唯一文件名
    file_id = str(uuid.uuid4())
    ext = file_type
    safe_filename = f"{file_id}.{ext}"
    file_path = REPORT_DIR / safe_filename
    
    # 保存文件
    with open(file_path, "wb") as f:
        f.write(contents)
    
    # 提取文本内容
    extracted_text = await extract_text_from_file(file_path, file_type)
    
    return UploadResponse(
        success=True,
        file_id=file_id,
        file_name=file.filename,
        file_type=file_type,
        file_size=file_size,
        extracted_text=extracted_text,
        message="文件上传成功"
    )


@router.post("/analyze", response_model=AnalysisResponse)
async def analyze_report(file_id: str):
    """
    分析已上传的报告，提取异常指标
    
    - 需要先上传文件获取 file_id
    - 使用 LLM 分析文本内容
    - 返回结构化的异常指标
    """
    # 查找文件
    file_path = None
    for ext in ["pdf", "png", "jpg", "jpeg"]:
        potential_path = REPORT_DIR / f"{file_id}.{ext}"
        if potential_path.exists():
            file_path = potential_path
            break
    
    if not file_path:
        raise HTTPException(status_code=404, detail="文件不存在")
    
    # 提取文本
    extracted_text = await extract_text_from_file(file_path, file_path.suffix[1:])
    
    if not extracted_text:
        return AnalysisResponse(
            success=False,
            file_id=file_id,
            analysis={},
            message="未能提取到文本内容"
        )
    
    # 使用 LLM 分析异常指标
    analysis = await analyze_medical_indicators(extracted_text)
    
    return AnalysisResponse(
        success=True,
        file_id=file_id,
        analysis=analysis,
        message="分析完成"
    )


async def extract_text_from_file(file_path: Path, file_type: str) -> str:
    """从文件提取文本内容"""
    try:
        if file_type == "pdf":
            return extract_text_from_pdf(file_path)
        elif file_type in ["png", "jpg", "jpeg"]:
            return await extract_text_from_image(file_path)
        return ""
    except Exception as e:
        logger.error(f"提取文本失败: {e}")
        return ""


def extract_text_from_pdf(pdf_path: Path) -> str:
    """从 PDF 提取文本"""
    try:
        import pdfplumber
        
        text_parts = []
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text_parts.append(page_text)
        
        return "\n".join(text_parts)
    except ImportError:
        logger.info("pdfplumber 未安装，尝试使用 PyPDF2")
        try:
            import PyPDF2
            
            text_parts = []
            with open(pdf_path, "rb") as f:
                reader = PyPDF2.PdfReader(f)
                for page in reader.pages:
                    text_parts.append(page.extract_text())
            
            return "\n".join(text_parts)
        except ImportError:
            logger.info("PyPDF2 也未安装")
            return ""
    except Exception as e:
        logger.error(f"PDF 解析错误: {e}")
        return ""


async def extract_text_from_image(image_path: Path) -> str:
    """从图片提取文本（OCR）"""
    # 首先尝试使用 Tesseract（本地）
    tesseract_text = await try_tesseract_ocr(image_path)
    if tesseract_text:
        return tesseract_text
    
    # 如果 Tesseract 不可用，使用在线 OCR
    online_text = await try_online_ocr(image_path)
    if online_text:
        return online_text
    
    return "[无法识别图片文字，请安装 Tesseract OCR 或上传 PDF 格式]"


async def try_tesseract_ocr(image_path: Path) -> str:
    """尝试使用 Tesseract OCR"""
    try:
        from PIL import Image
        import pytesseract
        
        # 尝试常见的 Tesseract 安装路径
        tesseract_paths = [
            r'D:\Tesseract-OCR\tesseract.exe',
            r'C:\Program Files\Tesseract-OCR\tesseract.exe',
            r'C:\Program Files (x86)\Tesseract-OCR\tesseract.exe',
        ]
        
        for path in tesseract_paths:
            import os
            if os.path.exists(path):
                pytesseract.pytesseract.tesseract_cmd = path
                break
        
        image = Image.open(image_path)
        text = pytesseract.image_to_string(image, lang='chi_sim+eng')
        result = text.strip()
        
        if result and len(result) > 5:
            return result
        return ""
    except ImportError:
        logger.info("Tesseract OCR 未安装或未配置")
        return ""
    except Exception as e:
        logger.error(f"Tesseract OCR 错误: {e}")
        return ""


async def try_online_ocr(image_path: Path) -> str:
    """使用免费的在线 OCR API"""
    logger.info(f"🚀 开始在线 OCR，文件: {image_path}")
    
    # 首先尝试 MinerU SDK（免登录，最简单）
    logger.info("   尝试 1: MinerU SDK...")
    mineru_result = await try_mineru_online_api(image_path)
    if mineru_result:
        logger.info(f"   ✅ MinerU SDK 成功")
        return mineru_result
    
    # 其次尝试本地 MinerU（如果可用）
    logger.info("   尝试 2: 本地 MinerU...")
    mineru_local_result = await try_mineru_ocr(image_path)
    if mineru_local_result:
        logger.info(f"   ✅ 本地 MinerU 成功")
        return mineru_local_result
    
    # 备用方案：在线 OCR
    logger.info("   尝试 3: OCR.space API...")
    try:
        from config import get_settings
        settings = get_settings()
        if not settings.ocr_space_api_key:
            logger.info("   ⚠️ OCR.space API Key 未配置，跳过 OCR.space")
            return ""

        import requests
        
        with open(image_path, "rb") as f:
            files = {"file": f}
            data = {
                "language": "chs",
                "isOverlayRequired": False,
                "detectOrientation": True,
                "scale": True,
            }
            response = requests.post(
                "https://api.ocr.space/parse/image",
                headers={"apikey": settings.ocr_space_api_key},
                data=data,
                files=files,
                timeout=30
            )
        
        result = response.json()
        
        if result.get("ParsedResults"):
            raw_text = result["ParsedResults"][0].get("ParsedText", "")
            cleaned_text = clean_ocr_text(raw_text)
            logger.info(f"   ✅ OCR.space API 成功")
            return cleaned_text
        
        return ""
    except Exception as e:
        logger.error(f"   ❌ 所有在线 OCR 都失败了")
        return ""


async def try_mineru_online_api(image_path: Path) -> str:
    """使用 MinerU Python SDK（免登录，Flash模式）"""
    logger.info(f"   🔍 [MinerU SDK] 开始调用...")
    try:
        # 导入 MinerU SDK
        from mineru import MinerU
        
        # 不传 Token，自动进入 flash-only 模式（免登录）
        logger.info(f"   🔍 [MinerU SDK] 初始化客户端...")
        client = MinerU()
        
        # 使用 flash_extract 提取文档
        logger.info(f"   🔍 [MinerU SDK] 正在解析文件: {image_path}")
        result = client.flash_extract(str(image_path))
        
        # 获取 markdown 内容
        if result and hasattr(result, 'markdown'):
            markdown_text = result.markdown
            logger.info(f"   ✅ [MinerU SDK] 解析成功，长度: {len(markdown_text)} 字符")
            return clean_ocr_text(markdown_text)
        else:
            logger.info(f"   ❌ [MinerU SDK] 未获取到有效结果")
            return ""
            
    except ImportError:
        logger.info(f"   ❌ [MinerU SDK] 未安装，请运行: pip install mineru-open-sdk")
        return ""
    except Exception as e:
        logger.error(f"   ❌ [MinerU SDK] 异常: {e}")
        import traceback
        traceback.print_exc()
        return ""


async def try_mineru_ocr(image_path: Path) -> str:
    """尝试使用 MinerU（文档解析工具，支持表格识别）"""
    # 首先尝试使用本地 API (http://127.0.0.1:16446)
    result = await try_mineru_api(image_path)
    if result:
        return result
    # 如果 API 失败，尝试使用 CLI
    return await try_mineru_cli(image_path)


async def try_mineru_api(image_path: Path) -> str:
    """使用本地 MinerU API 方式调用 (http://127.0.0.1:16446)"""
    try:
        import requests

        api_url = "http://127.0.0.1:16446/analyze"
        with open(image_path, 'rb') as f:
            files = {'file': f}
            data = {'output_format': 'markdown'}
            response = requests.post(api_url, files=files, data=data, timeout=120)
        
        if response.status_code == 200:
            result = response.json()
            # 尝试从响应中提取文本内容
            if isinstance(result, dict):
                # 根据API文档，响应可能包含 markdown 内容
                text = result.get('markdown', '') or result.get('text', '') or str(result)
            else:
                text = str(result)
            return clean_ocr_text(text)
        return ""
    except Exception as e:
        logger.error(f"MinerU API 错误: {e}")
        return ""


async def try_mineru_cli(image_path: Path) -> str:
    """使用 CLI 方式调用 MinerU"""
    try:
        import subprocess
        import asyncio

        # 使用 asyncio.create_subprocess_shell 异步调用
        process = await asyncio.create_subprocess_shell(
            f"mineru parse \"{image_path}\" --format markdown",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )

        # 修复：communicate() 不接受 timeout 参数，使用 asyncio.wait_for 包裹
        try:
            # 创建一个任务来运行 communicate
            async def run_communicate():
                return await process.communicate()
            
            # 设置超时
            stdout, stderr = await asyncio.wait_for(run_communicate(), timeout=120)
        except asyncio.TimeoutError:
            process.kill()
            logger.info("MinerU CLI 超时")
            return ""

        if process.returncode == 0:
            if stdout:
                return clean_ocr_text(stdout.decode('utf-8'))

        return ""
    except Exception as e:
        logger.error(f"MinerU CLI 错误: {e}")
        return ""


def clean_ocr_text(text: str) -> str:
    """清理 OCR 识别的文本，标准化表格数据"""
    import re
    
    lines = text.split('\n')
    cleaned_lines = []
    
    # 收集所有数据行
    data_lines = []
    for line in lines:
        if not line.strip():
            continue
        
        # 标准化数字中的特殊字符
        line = re.sub(r'，', '.', line)  # 中文逗号转英文点
        line = re.sub(r'一一', '-', line)  # 中文破折号转连字符
        line = re.sub(r'一', '-', line)   # 中文横线转连字符
        line = re.sub(r'、', '.', line)   # 中文顿号转英文点
        
        # 清理多余空格
        line = re.sub(r'\s+', ' ', line).strip()
        
        # 如果行太短，可能是表头，跳过
        if len(line) < 2:
            continue
            
        data_lines.append(line)
    
    # 尝试智能重组表格数据
    result = try_reconstruct_table(data_lines)
    
    # 添加结构化标记
    if result:
        result = "【检查报告 - 表格数据】\n" + result
        result += "\n\n注：以上为识别到的表格数据，请根据上下文解析。"
    else:
        result = "\n".join(data_lines)
    
    return result


def try_reconstruct_table(lines):
    """尝试从混乱的OCR结果中重建表格结构"""
    import re
    
    common_codes = {
        'WBC': '白细胞数', 'NEU%': '中性粒细胞百分比', 'LYM%': '淋巴细胞百分比',
        'MON%': '单核细胞百分比', 'EOS%': '嗜酸性粒细胞百分比', 'BAS%': '嗜碱性粒细胞百分比',
        'NEU#': '中性粒细胞绝对值', 'LYM#': '淋巴细胞绝对值', 'MON#': '单核细胞绝对值',
        'EOS#': '嗜酸性粒细胞绝对值', 'BAS#': '嗜碱性粒细胞绝对值',
        'RBC': '红细胞数', 'HGB': '血红蛋白', 'HCT': '红细胞压积',
        'MCV': '红细胞平均体积', 'MCH': '平均红细胞血红蛋白含量', 'MCHC': '平均红细胞血红蛋白浓度',
        'RDW-SD': '红细胞体积分布宽度SD', 'RDW-CV': '红细胞体积分布宽度CV',
        'PLT': '血小板数', 'PCT': '血小板压积', 'MPV': '平均血小板体积',
        'PDW': '血小板体积分布宽度', 'P-LCR': '大型血小板比率',
        'IG%': '未成熟粒细胞比值', 'IG#': '未成熟粒细胞绝对值',
        'NRBC%': '有核红细胞百分比', 'NRBC#': '有核红细胞绝对值'
    }
    
    # 先收集所有指标和数值
    indicators = []
    code_pattern = r'^(WBC|NEU[%#]|LYM[%#]|MON[%#]|EOS[%#]|BAS[%#]|RBC|HGB|HCT|MCV|MCH|MCHC|RDW-SD|RDW-CV|PLT|PCT|MPV|PDW|P-LCR|IG[%#]|NRBC[%#])$'
    
    for line in lines:
        line = line.strip()
        if re.match(code_pattern, line):
            indicators.append({'code': line, 'values': []})
        elif indicators:
            # 提取数值
            values = extract_values(line)
            if values:
                indicators[-1]['values'].extend(values)
    
    # 如果找到了指标，格式化输出
    if indicators:
        result_lines = []
        for ind in indicators:
            result_lines.append(format_indicator(ind['code'], ind['values']))
        return '\n'.join(result_lines)
    
    # 如果没有找到指标，尝试另一种方法：根据关键字识别
    return try_alternative_parse(lines)


def try_alternative_parse(lines):
    """备选解析方法：根据行内容推断"""
    import re
    
    # 常见指标名称
    indicator_names = [
        '白细胞数', '中性粒细胞百分比', '淋巴细胞百分比', '单核细胞百分比',
        '嗜酸性粒细胞百分比', '嗜碱性粒细胞百分比',
        '中性粒细胞绝对值', '淋巴细胞绝对值', '单核细胞绝对值',
        '嗜酸性粒细胞绝对值', '嗜碱性粒细胞绝对值',
        '红细胞数', '血红蛋白', '红细胞压积',
        '红细胞平均体积', '平均红细胞血红蛋白含量', '平均红细胞血红蛋白浓度',
        '红细胞体积分布宽度SD', '红细胞体积分布宽度CV',
        '血小板数', '血小板压积', '平均血小板体积',
        '血小板体积分布宽度', '大型血小板比率'
    ]
    
    result_lines = []
    current_name = None
    current_values = []
    
    for line in lines:
        line = line.strip()
        
        # 检查是否是指标名称
        found_name = None
        for name in indicator_names:
            if name in line or line in name:
                found_name = name
                break
        
        if found_name:
            # 保存上一个指标
            if current_name and current_values:
                result_lines.append(f"{current_name}: {', '.join(current_values)}")
            
            current_name = found_name
            current_values = []
        else:
            # 提取数值
            if current_name:
                values = extract_values(line)
                current_values.extend(values)
    
    if current_name and current_values:
        result_lines.append(f"{current_name}: {', '.join(current_values)}")
    
    return '\n'.join(result_lines) if result_lines else ""


def extract_values(line):
    """从行中提取数值和参考范围"""
    import re
    
    values = []
    
    # 匹配数字（可能包含小数点、负号、箭头）
    # 匹配格式: 数字 或 数字-数字（范围）
    patterns = [
        r'(\d+\.?\d*)\s*-\s*(\d+\.?\d*)',  # 范围如 "3.5-9.5"
        r'(\d+\.?\d*)\s*~?\s*(\d+\.?\d*)',  # 范围如 "3.5~9.5"
        r'(\d+\.?\d*)',                      # 单个数字
        r'([<>≤≥≈])\s*(\d+\.?\d*)',         # 带比较符的数字
    ]
    
    for pattern in patterns:
        matches = re.findall(pattern, line)
        for match in matches:
            if isinstance(match, tuple):
                values.append('-'.join(match))  # 范围
            else:
                values.append(match)
    
    return values


def format_indicator(code, values):
    """格式化指标行"""
    common_codes = {
        'WBC': '白细胞数', 'NEU%': '中性粒细胞百分比', 'LYM%': '淋巴细胞百分比',
        'MON%': '单核细胞百分比', 'EOS%': '嗜酸性粒细胞百分比', 'BAS%': '嗜碱性粒细胞百分比',
        'NEU#': '中性粒细胞绝对值', 'LYM#': '淋巴细胞绝对值', 'MON#': '单核细胞绝对值',
        'EOS#': '嗜酸性粒细胞绝对值', 'BAS#': '嗜碱性粒细胞绝对值',
        'RBC': '红细胞数', 'HGB': '血红蛋白', 'HCT': '红细胞压积',
        'MCV': '红细胞平均体积', 'MCH': '平均红细胞血红蛋白含量', 'MCHC': '平均红细胞血红蛋白浓度',
        'RDW-SD': '红细胞体积分布宽度SD', 'RDW-CV': '红细胞体积分布宽度CV',
        'PLT': '血小板数', 'PCT': '血小板压积', 'MPV': '平均血小板体积',
        'PDW': '血小板体积分布宽度', 'P-LCR': '大型血小板比率'
    }
    
    name = common_codes.get(code, code)
    
    # 尝试区分检测值和参考范围
    if len(values) >= 2:
        # 通常第一个是检测值，第二个是参考范围
        return f"{code} {name}: {values[0]}，参考范围: {values[1]}"
    elif len(values) == 1:
        return f"{code} {name}: {values[0]}"
    else:
        return f"{code} {name}"


async def analyze_medical_indicators(text: str) -> dict:
    """使用 LLM 分析医学指标，提取异常值"""
    try:
        import os
        from openai import OpenAI
        
        client = OpenAI(
            api_key=os.getenv("DASHSCOPE_API_KEY"),
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1"
        )
        
        prompt = f"""你是一个专业的医学报告分析助手。请分析以下检查报告文本，提取异常指标。

要求：
1. 识别报告中所有检查项目
2. 标注正常和异常项目
3. 重点关注异常值，给出参考范围
4. 如果有重大异常，标记为"需要关注"

输出格式要求：
- 返回 JSON 格式
- 包含字段：indicators（指标列表）、summary（总结）、Alerts（需要关注的项）

检查报告文本：
{text}

请以 JSON 格式返回分析结果。"""
        
        response = client.chat.completions.create(
            model="qwen-plus",
            messages=[
                {"role": "system", "content": "你是一个专业的医学报告分析助手，擅长解读各种检查报告。"},
                {"role": "user", "content": prompt}
            ],
            response_format={"type": "json_object"}
        )
        
        result = response.choices[0].message.content
        return json.loads(result)
        
    except Exception as e:
        logger.error(f"LLM 分析错误: {e}")
        return {
            "indicators": [],
            "summary": "自动分析失败，请人工查看原始报告",
            "alerts": [],
            "error": str(e)
        }


@router.get("/list")
async def list_uploads():
    """获取已上传文件列表"""
    files = []
    for f in REPORT_DIR.iterdir():
        if f.is_file():
            stat = f.stat()
            files.append({
                "file_id": f.stem,
                "file_name": f.name,
                "file_type": f.suffix[1:],
                "file_size": stat.st_size,
                "created_at": datetime.fromtimestamp(stat.st_ctime).isoformat()
            })
    
    return {"success": True, "files": files}


@router.delete("/{file_id}")
async def delete_upload(file_id: str):
    """删除已上传的文件"""
    deleted = False
    for ext in ["pdf", "png", "jpg", "jpeg"]:
        file_path = REPORT_DIR / f"{file_id}.{ext}"
        if file_path.exists():
            file_path.unlink()
            deleted = True
            break
    
    if not deleted:
        raise HTTPException(status_code=404, detail="文件不存在")
    
    return {"success": True, "message": "文件已删除"}
