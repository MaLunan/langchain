"""
Moonshot / Kimi 共享配置。

仅保留数字人工作流所需的最小能力：
- 读取 `.env`
- 构建一个 OpenAI 兼容的 Kimi 客户端，供文本改写复用
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI


def project_root() -> Path:
    return Path(__file__).resolve().parent


def load_env() -> None:
    """从项目根目录加载 `.env`，并校验 Moonshot API Key。"""
    env_path = project_root() / ".env"
    load_dotenv(env_path)

    key = (os.getenv("MOONSHOT_API_KEY") or "").strip()
    if not key:
        print(
            "\n【配置提示】程序主动退出：未检测到有效的 MOONSHOT_API_KEY。\n"
            f"1) 在项目根目录创建或编辑：{env_path}\n"
            "2) 写入一行（不要引号）：MOONSHOT_API_KEY=你的 Moonshot 密钥\n"
            "3) 也可先执行：cp .env.example .env 再编辑\n",
            file=sys.stderr,
        )
        sys.exit(1)
    os.environ["MOONSHOT_API_KEY"] = key


def build_moonshot_llm() -> ChatOpenAI:
    """构建工作流使用的 Kimi 客户端。"""
    return ChatOpenAI(
        base_url="https://api.moonshot.cn/v1",
        api_key=os.environ["MOONSHOT_API_KEY"],
        model=os.getenv("MOONSHOT_MODEL", "kimi-k2.5"),
        temperature=float(os.getenv("MOONSHOT_TEMPERATURE", "1")),
    )
