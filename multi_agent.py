"""
多角色 / 多 Agent 配置与自动路由。

思路简述：
- 「多角色」：每个角色一条独立 RunnableWithMessageHistory，各自一份会话记忆；同一 session_id 在不同角色下互不串话。
- 「调度」：可选地先让大模型根据用户话选一个 agent_id（多一次 Kimi 调用），再交给对应角色回答 —— 类似简易 Supervisor。
"""

from __future__ import annotations

from dataclasses import dataclass

# 先加载 rag_chat，以应用其中的 warnings 过滤，再 import 其它 LangChain 子模块。
from rag_chat import build_moonshot_llm, build_vectorstore, load_env, make_session_store, project_root

from langchain_community.vectorstores import FAISS
from langchain_core.messages import HumanMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.runnables import RunnablePassthrough
from langchain_core.runnables.history import RunnableWithMessageHistory
from langchain_openai import ChatOpenAI

from search_tools import search_web_duckduckgo


@dataclass(frozen=True)
class AgentProfile:
    """单个「角色」：系统设定 + 是否走本地知识库 + 是否联网搜索。"""

    agent_id: str
    display_name: str
    description: str
    system_instruction: str
    use_rag: bool = True
    use_web: bool = False


# 可按需增删；description 会出现在 /agents 与自动路由提示里。
BUILTIN_AGENT_PROFILES: tuple[AgentProfile, ...] = (
    AgentProfile(
        agent_id="assistant",
        display_name="资料助手",
        description="根据上传的知识库严谨作答，适合查产品说明、制度条款等。",
        system_instruction="你是友好的中文助手，表达简洁准确。",
        use_rag=True,
    ),
    AgentProfile(
        agent_id="tutor",
        display_name="小老师",
        description="用初中生能懂的方式讲解概念、给例题思路，适合学习辅导场景。",
        system_instruction=(
            "你是耐心的中文小老师，面向初中生。用短句、例子帮助理解；"
            "若知识库里有相关内容可引用；不要直接代写整篇作业。"
        ),
        use_rag=True,
    ),
    AgentProfile(
        agent_id="chat",
        display_name="闲聊伙伴",
        description="轻松聊天、脑洞、情感陪伴，不强制查资料。",
        system_instruction="你是轻松友好的聊天伙伴，口语化自然；不必引用资料，常识性回答即可。",
        use_rag=False,
        use_web=False,
    ),
    AgentProfile(
        agent_id="research",
        display_name="联网检索",
        description="时事、新闻、最新政策等需要上网查时用 DuckDuckGo 抓网页摘要再回答。",
        system_instruction=(
            "你是严谨的中文助手。请根据下方「网络搜索摘要」回答；"
            "摘要可能不全或过时，需说明信息来自网络并提醒用户核实。"
        ),
        use_rag=False,
        use_web=True,
    ),
)


def _profiles_by_id() -> dict[str, AgentProfile]:
    return {p.agent_id: p for p in BUILTIN_AGENT_PROFILES}


def build_agent_chain(
    vectorstore: FAISS,
    profile: AgentProfile,
    llm: ChatOpenAI,
) -> RunnableWithMessageHistory:
    """为单个角色组装「本地 RAG / 联网搜索（可选）+ 多轮记忆 + Kimi」链。"""
    retriever = (
        vectorstore.as_retriever(search_kwargs={"k": 4}) if profile.use_rag else None
    )

    def format_context(docs):
        return "\n\n".join(d.page_content for d in docs)

    def build_reference(user_input: str) -> str:
        blocks: list[str] = []
        if profile.use_rag and retriever is not None:
            ctx = format_context(retriever.invoke(user_input))
            blocks.append(
                "【本地参考资料】\n"
                + ctx
                + "\n\n请优先依据本地资料；不足以判断时要明确说不知道，不要编造。"
            )
        if profile.use_web:
            web = search_web_duckduckgo(user_input)
            blocks.append(
                "【网络搜索摘要（DuckDuckGo，可能不完整）】\n"
                + web
                + "\n\n请批判性使用，并在回答中说明信息来自网络检索。"
            )
        if not blocks:
            return "（本轮未检索本地文档，也未联网搜索；请仅依据对话与常识回答。）"
        return "\n\n".join(blocks)

    enrich = RunnablePassthrough.assign(
        reference=lambda x: build_reference(x["input"]),
    )

    full_system = profile.system_instruction + "\n\n{reference}"
    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", full_system),
            MessagesPlaceholder("chat_history"),
            ("human", "{input}"),
        ]
    )
    chain = enrich | prompt | llm

    return RunnableWithMessageHistory(
        chain,
        make_session_store(),
        input_messages_key="input",
        history_messages_key="chat_history",
    )


def create_agent_hub() -> tuple[dict[str, RunnableWithMessageHistory], ChatOpenAI]:
    """
    构建所有内置角色链，并返回共享的 LLM（给自动路由复用，避免重复构造客户端）。

    返回 (agent_id -> chain, llm)。
    """
    load_env()
    vs = build_vectorstore(project_root() / "data")
    llm = build_moonshot_llm()
    hub = {p.agent_id: build_agent_chain(vs, p, llm) for p in BUILTIN_AGENT_PROFILES}
    return hub, llm


def suggest_agent_for_message(message: str, llm: ChatOpenAI) -> str:
    """
    调度用：根据用户输入选一个 agent_id。会消耗一次 LLM 调用。

    若解析失败则回退到 assistant。
    """
    lines = "\n".join(f"- {p.agent_id}: {p.description}" for p in BUILTIN_AGENT_PROFILES)
    router_prompt = (
        "你是调度员。根据用户最新一句话，只回复一个 agent_id，不要其它文字或标点。\n\n"
        f"可选角色：\n{lines}\n\n用户说：{message}\nagent_id："
    )
    resp = llm.invoke([HumanMessage(content=router_prompt)])
    raw = (resp.content or "").strip().lower()
    valid = _profiles_by_id()
    for aid in valid:
        if raw == aid or raw.startswith(aid + " ") or aid in raw.split():
            return aid
    return "assistant"
