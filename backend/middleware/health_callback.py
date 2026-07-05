"""
智能健康助手中间件
LangChain BaseCallbackHandler — 织入全链路LLM调用
功能：敏感信息脱敏、异常捕获重试、Token统计、Agent思考推送
"""

import re
import logging
logger = logging.getLogger(__name__)
import time
from typing import Any, Dict, List
from langchain_core.callbacks import BaseCallbackHandler


class HealthAgentCallback(BaseCallbackHandler):
    """健康助手全链路回调处理器"""

    def __init__(self, verbose: bool = True):
        super().__init__()
        self.verbose = verbose
        self.total_tokens = 0
        self.prompt_tokens = 0
        self.completion_tokens = 0
        self.llm_call_count = 0
        self.consultation_round = 0
        self.max_consultation_rounds = 10
        self.error_count = 0
        self.max_retries = 3

    # ============ 脱敏 ============

    def _desensitize(self, text: str) -> str:
        """敏感信息脱敏"""
        patterns = {
            "身份证": (r'\b\d{17}[\dXx]\b', '[身份证已脱敏]'),
            "手机号": (r'\b1[3-9]\d{9}\b', '[手机号已脱敏]'),
            "姓名": (r'(姓名[:：])\s*[\u4e00-\u9fa5]{2,4}', r'\1[姓名已脱敏]'),
            "住址": (r'(地址[:：])\s*.{5,30}', r'\1[地址已脱敏]'),
        }
        for name, (pattern, replacement) in patterns.items():
            if re.search(pattern, text):
                text = re.sub(pattern, replacement, text)
                if self.verbose:
                    logger.info(f"   🔒 脱敏: {name}")
        return text

    # ============ LLM 回调 ============

    def on_llm_start(self, serialized: Dict[str, Any], prompts: List[str], **kwargs) -> None:
        """LLM 调用开始"""
        self.llm_call_count += 1
        # 脱敏输入
        for i, prompt in enumerate(prompts):
            prompts[i] = self._desensitize(prompt)

    def on_llm_end(self, response, **kwargs) -> None:
        """LLM 调用结束 — Token 统计"""
        try:
            usage = response.llm_output.get("token_usage", {})
            prompt_tok = usage.get("prompt_tokens", 0)
            comp_tok = usage.get("completion_tokens", 0)
            self.prompt_tokens += prompt_tok
            self.completion_tokens += comp_tok
            self.total_tokens += prompt_tok + comp_tok
        except Exception:
            pass

    # ============ Agent 回调 ============

    def on_agent_action(self, action, **kwargs) -> None:
        """Agent 工具调用 — 思考过程推送"""
        if self.verbose:
            logger.info(f"   💭 Agent思考: 调用工具 [{action.tool}] — {action.tool_input[:80]}...")

    def on_agent_finish(self, finish, **kwargs) -> None:
        """Agent 完成 — 问诊轮数检查"""
        self.consultation_round += 1
        if self.verbose:
            logger.info(f"   ✅ Agent完成 (第{self.consultation_round}轮)")

    # ============ 异常处理 ============

    def on_chain_error(self, error: Exception, **kwargs) -> None:
        """Chain 异常 — 记录+降级"""
        self.error_count += 1
        logger.error(f"   ⚠️ 异常捕获 (第{self.error_count}次): {str(error)[:100]}")

    def should_retry(self) -> bool:
        """判断是否应该重试"""
        return self.error_count < self.max_retries

    def is_consultation_timeout(self) -> bool:
        """判断问诊是否超时"""
        return self.consultation_round >= self.max_consultation_rounds

    # ============ 统计 ============

    def get_stats(self) -> dict:
        """获取统计摘要"""
        return {
            "llm_call_count": self.llm_call_count,
            "total_tokens": self.total_tokens,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "consultation_rounds": self.consultation_round,
            "error_count": self.error_count,
        }

    def print_stats(self):
        """打印统计摘要"""
        stats = self.get_stats()
        logger.info(f"\n📊 中间件统计:")
        logger.info(f"   LLM调用: {stats['llm_call_count']} 次")
        logger.info(f"   Token消耗: {stats['total_tokens']} (输入{stats['prompt_tokens']}+输出{stats['completion_tokens']})")
        logger.info(f"   问诊轮数: {stats['consultation_rounds']}")
        logger.error(f"   异常次数: {stats['error_count']}")