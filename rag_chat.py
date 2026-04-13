"""
Kimi（Moonshot）+ 多轮记忆 + 本地文本 RAG 的核心逻辑。

main.py / server.py 只负责 CLI 或 HTTP 入口，避免两处重复维护同一条链。
"""

from __future__ import annotations

import os
import sys
import warnings
from pathlib import Path

# Python 3.14 下 LangChain 仍会触发 Pydantic v1 的兼容性提示；不影响多数用法，先压掉以免误以为报错。
warnings.filterwarnings(
    "ignore",
    message=r"Core Pydantic V1 functionality isn't compatible with Python 3\.14 or greater\.",
    category=UserWarning,
)

from dotenv import load_dotenv
from langchain_community.vectorstores import FAISS
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_openai import ChatOpenAI
from langchain_text_splitters import RecursiveCharacterTextSplitter


def project_root() -> Path:
    """项目根目录（与 rag_chat.py 所在目录一致）。"""
    return Path(__file__).resolve().parent


def load_env() -> None:
    """从项目根目录读取 .env，避免把密钥写进代码。"""
    env_path = project_root() / ".env"
    load_dotenv(env_path)

    key = (os.getenv("MOONSHOT_API_KEY") or "").strip()
    if not key:
        print(
            "\n【配置提示】程序主动退出：未检测到有效的 MOONSHOT_API_KEY（不是 Python 语法错误）。\n"
            f"1) 在项目根目录创建或编辑：{env_path}\n"
            "2) 写入一行（不要引号）：MOONSHOT_API_KEY=你在 https://platform.moonshot.cn 申请的密钥\n"
            "3) 也可先执行：cp .env.example .env 再编辑 .env 填密钥\n",
            file=sys.stderr,
        )
        sys.exit(1)
    os.environ["MOONSHOT_API_KEY"] = key


def build_vectorstore(data_dir: Path) -> FAISS:
    """
    TextSplitter：按字符递归切分，保留重叠（overlap）可减少「句子被切断」导致的语义丢失。
    FAISS：内存向量索引，适合本地原型；生产环境可换 pgvector、Milvus 等。
    """
    texts: list[str] = []
    for path in sorted(data_dir.glob("*.txt")):
        texts.append(path.read_text(encoding="utf-8"))

    if not texts:
        raise FileNotFoundError(f"在 {data_dir} 下未找到任何 .txt，请放入知识文件。")

    splitter = RecursiveCharacterTextSplitter(chunk_size=400, chunk_overlap=80)
    docs = splitter.create_documents(texts)

    # 多语言小模型：中文问答足够做演示；CPU 可跑，首次会从 Hugging Face 下载权重。
    # 若访问 huggingface.co 较慢，可在 .env 中设置 HF_ENDPOINT=https://hf-mirror.com（镜像，按需使用）。
    embeddings = HuggingFaceEmbeddings(
        model_name="sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
        model_kwargs={"local_files_only": True},
    )
    return FAISS.from_documents(docs, embeddings)


def make_session_store():
    """用内存字典存历史；重启进程即清空。持久化可换 RedisChatMessageHistory 等。"""
    from langchain_community.chat_message_histories import ChatMessageHistory

    store: dict[str, ChatMessageHistory] = {}

    def get_session_history(session_id: str) -> ChatMessageHistory:
        if session_id not in store:
            store[session_id] = ChatMessageHistory()
        return store[session_id]

    return get_session_history


def build_moonshot_llm() -> ChatOpenAI:
    """
    统一的 Kimi 客户端。Moonshot 对部分模型要求 temperature 只能为 1，否则会 400。
    """
    return ChatOpenAI(
        base_url="https://api.moonshot.cn/v1",
        api_key=os.environ["MOONSHOT_API_KEY"],
        model=os.getenv("MOONSHOT_MODEL", "kimi-k2.5"),
        temperature=float(os.getenv("MOONSHOT_TEMPERATURE", "1")),
    )


def create_rag_chain():
    """
    兼容旧入口：只返回默认「资料助手」链。

    多角色请用 multi_agent.create_agent_hub()。
    """
    from multi_agent import create_agent_hub

    hub, _llm = create_agent_hub()
    return hub["assistant"]
