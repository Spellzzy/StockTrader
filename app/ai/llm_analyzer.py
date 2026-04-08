"""LLM 分析引擎 — 调用大语言模型生成股票分析报告

支持多个 LLM 后端:
    1. OpenAI API (GPT-4 / GPT-4o)
    2. 兼容 OpenAI 格式的第三方 (DeepSeek / 通义千问 / 月之暗面)
    3. 本地 Ollama (Qwen / Llama)  ← 免费方案

用法:
    analyzer = LLMAnalyzer()
    report = analyzer.analyze("sh600519")
"""

import json
import logging
from dataclasses import dataclass, field
from typing import Optional

from app.ai.prompt_builder import PromptBuilder
from app.config import get_config

logger = logging.getLogger(__name__)


@dataclass
class AnalysisReport:
    """LLM 分析报告的结构化表示"""
    code: str = ""
    technical_analysis: str = ""
    fundamental_analysis: str = ""
    money_flow_analysis: str = ""
    news_sentiment: str = "neutral"
    news_summary: str = ""
    short_term_view: str = ""
    mid_term_view: str = ""
    risk_warnings: list = field(default_factory=list)
    confidence: int = 0
    overall_rating: str = "中性"
    raw_response: str = ""
    error: str = ""

    @classmethod
    def from_dict(cls, data: dict, code: str = "") -> "AnalysisReport":
        """从 LLM JSON 响应构造"""
        return cls(
            code=code,
            technical_analysis=data.get("technical_analysis", ""),
            fundamental_analysis=data.get("fundamental_analysis", ""),
            money_flow_analysis=data.get("money_flow_analysis", ""),
            news_sentiment=data.get("news_sentiment", "neutral"),
            news_summary=data.get("news_summary", ""),
            short_term_view=data.get("short_term_view", ""),
            mid_term_view=data.get("mid_term_view", ""),
            risk_warnings=data.get("risk_warnings", []),
            confidence=int(data.get("confidence", 0)),
            overall_rating=data.get("overall_rating", "中性"),
        )

    def to_dict(self) -> dict:
        """转换为 dict"""
        return {
            "code": self.code,
            "technical_analysis": self.technical_analysis,
            "fundamental_analysis": self.fundamental_analysis,
            "money_flow_analysis": self.money_flow_analysis,
            "news_sentiment": self.news_sentiment,
            "news_summary": self.news_summary,
            "short_term_view": self.short_term_view,
            "mid_term_view": self.mid_term_view,
            "risk_warnings": self.risk_warnings,
            "confidence": self.confidence,
            "overall_rating": self.overall_rating,
        }


class LLMAnalyzer:
    """LLM 分析引擎 — 支持多后端"""

    def __init__(self):
        self.prompt_builder = PromptBuilder()
        self._config = get_config().get("ai", {}).get("llm", {})

    @property
    def provider(self) -> str:
        return self._config.get("provider", "openai")

    @property
    def api_key(self) -> str:
        return self._config.get("api_key", "")

    @property
    def model(self) -> str:
        return self._config.get("model", "gpt-4")

    @property
    def base_url(self) -> str:
        return self._config.get("base_url", "")

    @property
    def is_configured(self) -> bool:
        """检查 LLM 是否已配置"""
        if self.provider == "ollama":
            return True  # Ollama 本地，不需要 API key
        return bool(self.api_key)

    # ==================== 公开接口 ====================

    def analyze(
        self,
        code: str,
        prediction_result: Optional[dict] = None,
    ) -> AnalysisReport:
        """对指定股票进行 LLM 深度分析

        Args:
            code: 股票代码
            prediction_result: ML/DL 预测结果（可选，由 PredictorService.predict() 返回）

        Returns:
            AnalysisReport 结构化分析报告
        """
        if not self.is_configured:
            return AnalysisReport(
                code=code,
                error=self._get_config_hint(),
            )

        # 1. 组装 Prompt
        prompt_data = self.prompt_builder.build_analysis_prompt(code, prediction_result)

        # 2. 调用 LLM
        try:
            raw_response = self._call_llm(
                system_prompt=prompt_data["system"],
                user_prompt=prompt_data["user"],
            )
        except Exception as e:
            logger.error(f"LLM 调用失败: {e}")
            return AnalysisReport(code=code, error=f"LLM 调用失败: {e}")

        # 3. 解析响应
        report = self._parse_response(raw_response, code)
        report.raw_response = raw_response
        return report

    def test_connection(self) -> dict:
        """测试 LLM 连接是否正常

        Returns:
            {"ok": bool, "message": str, "provider": str, "model": str}
        """
        if not self.is_configured:
            return {
                "ok": False,
                "message": self._get_config_hint(),
                "provider": self.provider,
                "model": self.model,
            }

        try:
            response = self._call_llm(
                system_prompt="You are a helpful assistant.",
                user_prompt="请回复'连接成功'四个字。",
            )
            return {
                "ok": True,
                "message": f"连接成功: {response[:50]}",
                "provider": self.provider,
                "model": self.model,
            }
        except Exception as e:
            return {
                "ok": False,
                "message": f"连接失败: {e}",
                "provider": self.provider,
                "model": self.model,
            }

    # ==================== LLM 调用层 ====================

    def _call_llm(self, system_prompt: str, user_prompt: str) -> str:
        """调用 LLM，根据 provider 分发到不同后端

        Returns:
            LLM 的原始文本响应
        """
        provider = self.provider.lower()

        if provider == "ollama":
            return self._call_ollama(system_prompt, user_prompt)
        else:
            # openai / deepseek / moonshot / dashscope 等兼容 OpenAI 格式
            return self._call_openai_compatible(system_prompt, user_prompt)

    def _call_openai_compatible(self, system_prompt: str, user_prompt: str) -> str:
        """调用 OpenAI 兼容 API (OpenAI / DeepSeek / 通义千问 / 月之暗面)"""
        import httpx

        # 根据 provider 确定 base_url
        base_url = self.base_url
        if not base_url:
            provider_urls = {
                "openai": "https://api.openai.com/v1",
                "deepseek": "https://api.deepseek.com/v1",
                "moonshot": "https://api.moonshot.cn/v1",
                "dashscope": "https://dashscope.aliyuncs.com/compatible-mode/v1",
                "zhipu": "https://open.bigmodel.cn/api/paas/v4",
            }
            base_url = provider_urls.get(self.provider, "https://api.openai.com/v1")

        url = f"{base_url.rstrip('/')}/chat/completions"

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.3,
            "max_tokens": 2000,
        }

        # 如果模型支持 JSON mode
        if any(kw in self.model for kw in ["gpt-4", "gpt-3.5-turbo", "deepseek"]):
            payload["response_format"] = {"type": "json_object"}

        with httpx.Client(timeout=120) as client:
            resp = client.post(url, headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"]

    def _call_ollama(self, system_prompt: str, user_prompt: str) -> str:
        """调用本地 Ollama API"""
        import httpx

        base_url = self.base_url or "http://localhost:11434"
        url = f"{base_url.rstrip('/')}/api/chat"

        payload = {
            "model": self.model or "qwen2.5:7b",
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "stream": False,
            "format": "json",
            "options": {
                "temperature": 0.3,
                "num_predict": 2000,
            },
        }

        with httpx.Client(timeout=180) as client:
            resp = client.post(url, json=payload)
            resp.raise_for_status()
            data = resp.json()
            return data["message"]["content"]

    # ==================== 响应解析 ====================

    def _parse_response(self, raw: str, code: str) -> AnalysisReport:
        """解析 LLM 的 JSON 响应为 AnalysisReport"""
        try:
            # 尝试直接解析
            data = json.loads(raw)
            return AnalysisReport.from_dict(data, code)
        except json.JSONDecodeError:
            pass

        # 尝试提取 JSON 块 (```json ... ```)
        try:
            import re
            match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', raw, re.DOTALL)
            if match:
                data = json.loads(match.group(1))
                return AnalysisReport.from_dict(data, code)
        except (json.JSONDecodeError, AttributeError):
            pass

        # 尝试找到第一个 { 和最后一个 }
        try:
            start = raw.index("{")
            end = raw.rindex("}") + 1
            data = json.loads(raw[start:end])
            return AnalysisReport.from_dict(data, code)
        except (ValueError, json.JSONDecodeError):
            pass

        # 全部失败，返回原始文本
        logger.warning("LLM 响应解析失败，返回原始文本")
        return AnalysisReport(
            code=code,
            technical_analysis=raw[:500],
            error="JSON 解析失败，显示原始响应",
        )

    # ==================== 辅助 ====================

    def _get_config_hint(self) -> str:
        """获取配置提示"""
        return (
            "LLM 未配置。请在 config.yaml 中配置:\n"
            "  ai:\n"
            "    llm:\n"
            "      provider: openai        # openai/deepseek/moonshot/ollama\n"
            "      api_key: sk-xxx         # API Key (ollama 不需要)\n"
            "      model: gpt-4o           # 模型名称\n"
            "      base_url: ''            # 自定义 API 地址 (可选)\n"
            "\n"
            "免费方案: 安装 Ollama 后配置 provider: ollama, model: qwen2.5:7b"
        )
