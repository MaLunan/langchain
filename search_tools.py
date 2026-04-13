"""
联网搜索工具（供 Agent 在回答前拉取网页摘要）。

为什么用 DuckDuckGo？
  无需申请搜索 API Key，适合本地演示。部分网络环境可能访问失败，已做异常捕获。

生产环境可替换为 Tavily、SerpAPI、必应等（质量与稳定性通常更好，需密钥）。
"""

from __future__ import annotations


def search_web_duckduckgo(query: str) -> str:
    """
    使用 DuckDuckGo 返回文本摘要，供大模型综合回答。

    使用 DuckDuckGoSearchRun：返回单段字符串，比结构化结果更易塞进提示词。
    """
    query = (query or "").strip()
    if not query:
        return "（搜索关键词为空。）"

    try:
        from langchain_community.tools import DuckDuckGoSearchRun
    except ImportError as e:
        return f"（未安装搜索依赖：{e}；请执行 pip install duckduckgo-search）"

    try:
        tool = DuckDuckGoSearchRun()
        raw = tool.invoke(query)
    except Exception as e:
        return f"（搜索失败：{e}；可检查网络或更换搜索提供商。）"

    if not raw or not str(raw).strip():
        return "（未找到相关结果。）"
    return str(raw).strip()
