"""
内网大模型调用封装（OpenAI 兼容接口）。
默认接入 deepseek-v4-flash，地址由环境变量 LLM_API_URL 控制。
"""
from __future__ import annotations

import os
import logging
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

DEFAULT_LLM_URL = "http://10.8.75.206:8000/v1/chat/completions"
DEFAULT_MODEL = "deepseek-v4-flash"


def get_llm_url() -> str:
    return os.getenv("LLM_API_URL", DEFAULT_LLM_URL).rstrip("/")


def get_model_name() -> str:
    return os.getenv("LLM_MODEL", DEFAULT_MODEL)


async def chat_completion(
    messages: list[dict],
    model: Optional[str] = None,
    temperature: float = 0.7,
    max_tokens: int = 2048,
    timeout: float = 60.0,
) -> str:
    """
    调用内网 LLM 聊天接口，返回 assistant 文本内容。
    """
    url = get_llm_url()
    payload = {
        "model": model or get_model_name(),
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": False,
    }

    logger.info(f"调用 LLM: {url} model={payload['model']}")
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(url, json=payload, headers={"Content-Type": "application/json"})
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPStatusError as e:
        logger.error(f"LLM HTTP 错误 {e.response.status_code}: {e.response.text[:500]}")
        raise RuntimeError(f"模型服务返回错误 ({e.response.status_code}): {e.response.text[:200]}") from e
    except httpx.RequestError as e:
        logger.error(f"LLM 请求失败: {e}")
        raise RuntimeError(f"无法连接模型服务: {e}") from e

    choices = data.get("choices", [])
    if not choices:
        raise RuntimeError("模型返回为空，没有 choices")

    content = choices[0].get("message", {}).get("content", "")
    if isinstance(content, str):
        return content.strip()
    return str(content)


async def analyze_with_context(platform_summary: str, user_question: Optional[str] = None) -> str:
    """基于平台当前数据向模型提问，生成运维分析建议。"""
    system_prompt = (
        "你是一位网络运维专家，正在使用 NetOps 网络 AI 运维监控平台。"
        "请根据下面提供的平台实时数据，给出简洁、可操作的运维建议。"
        "如果没有异常，请给出优化建议；如果有告警，请分析根因和处置步骤。"
    )
    user_content = f"平台当前数据：\n{platform_summary}\n\n问题：{user_question or '请给出当前网络健康度和处置建议。'}"
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content},
    ]
    return await chat_completion(messages, temperature=0.5, max_tokens=2048)
