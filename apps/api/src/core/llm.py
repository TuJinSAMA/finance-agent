"""
统一的 LLM 调用封装（基于 LangChain + OpenRouter）。

使用 ChatOpenAI 通过 OpenRouter 代理访问多种模型。
默认模型 minimax/minimax-m2.5，调用方可按需切换。
"""

import json
import logging

from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

from src.core.config import settings

logger = logging.getLogger(__name__)

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


def get_llm(
    model: str | None = None,
    temperature: float | None = None,
    max_tokens: int | None = None,
) -> ChatOpenAI:
    """创建 ChatOpenAI 实例（通过 OpenRouter）。"""
    return ChatOpenAI(
        openai_api_key=settings.OPENROUTER_API_KEY,
        openai_api_base=OPENROUTER_BASE_URL,
        model=model or settings.LLM_MODEL,
        temperature=temperature if temperature is not None else settings.LLM_TEMPERATURE,
        max_tokens=max_tokens or settings.LLM_MAX_TOKENS,
    )


async def chat_json(
    system_prompt: str,
    user_prompt: str,
    *,
    model: str | None = None,
    temperature: float | None = None,
) -> dict:
    """
    向 LLM 发送请求并解析 JSON 响应。

    使用 JsonOutputParser 从响应中提取 JSON。
    如果模型直接返回 JSON 格式失败，会尝试从 markdown code block 中提取。
    """
    llm = get_llm(model=model, temperature=temperature)

    prompt = ChatPromptTemplate.from_messages([
        ("system", "{system_prompt}"),
        ("human", "{user_prompt}"),
    ])

    chain = prompt | llm

    try:
        response = await chain.ainvoke({
            "system_prompt": system_prompt,
            "user_prompt": user_prompt,
        })
        content = response.content
        return _parse_json_response(content)
    except Exception:
        logger.exception("LLM chat_json call failed")
        raise


def _parse_json_response(content: str) -> dict:
    """从 LLM 响应中提取 JSON，兼容 markdown code block 格式。"""
    text = content.strip()

    if text.startswith("```"):
        lines = text.split("\n")
        start = 1
        end = len(lines) - 1
        if lines[0].startswith("```json"):
            start = 1
        for i in range(len(lines) - 1, 0, -1):
            if lines[i].strip() == "```":
                end = i
                break
        text = "\n".join(lines[start:end]).strip()

    return json.loads(text)
