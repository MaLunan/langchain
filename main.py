"""CLI 入口：终端里与 Kimi 多角色 RAG 对话。核心逻辑见 rag_chat.py、multi_agent.py。"""

from __future__ import annotations

from multi_agent import BUILTIN_AGENT_PROFILES, create_agent_hub, suggest_agent_for_message


def main() -> None:
    print("正在构建向量索引与各角色链（首次会下载嵌入模型，可能稍慢）…")
    hub, router_llm = create_agent_hub()

    session_id = "demo-user"
    current_agent = "assistant"

    def print_agents() -> None:
        print("\n可选角色：")
        for p in BUILTIN_AGENT_PROFILES:
            print(f"  {p.agent_id:12} — {p.display_name}：{p.description}")
        print()

    print_agents()
    print(
        "命令：/agent 列出角色；/agent <id> 切换；/auto 本句自动选角（多一次模型调用）。\n"
        "输入 quit 退出。\n"
    )

    pending_auto = False

    while True:
        try:
            q = input("你：").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n再见。")
            return

        if q.lower() in {"quit", "exit", "q"}:
            print("再见。")
            return
        if not q:
            continue

        if q.lower() == "/auto":
            pending_auto = True
            print("已开启：下一条消息将自动选角。\n")
            continue

        if q.startswith("/agent"):
            parts = q.split(maxsplit=1)
            if len(parts) == 1:
                print_agents()
                print(f"当前角色：{current_agent}\n")
                continue
            new_id = parts[1].strip()
            if new_id not in hub:
                print(f"未知角色 id：{new_id}，请用 /agent 查看列表。\n")
                continue
            current_agent = new_id
            print(f"已切换到：{current_agent}\n")
            continue

        use_auto = pending_auto
        pending_auto = False

        if use_auto:
            picked = suggest_agent_for_message(q, router_llm)
            print(f"（自动选角：{picked}）")
            chain = hub[picked]
        else:
            chain = hub[current_agent]
            picked = current_agent

        out = chain.invoke(
            {"input": q},
            config={"configurable": {"session_id": session_id}},
        )
        print(f"Kimi[{picked}]：{out.content}\n")


if __name__ == "__main__":
    main()
