"""
工作流会话状态管理：跟踪从内容提取到视频生成的完整流程。

与 rag_chat.make_session_store() 同模式——内存字典，重启清空。
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Optional


class WorkflowStep(str, Enum):
    EXTRACTED = "extracted"
    REWRITTEN = "rewritten"
    CONFIRMED = "confirmed"
    AUDIO_DONE = "audio_done"
    VIDEO_DONE = "video_done"


@dataclass
class WorkflowState:
    session_id: str
    current_step: WorkflowStep
    source: str           # 原始输入（URL 或文件路径）
    source_type: str      # "url" 或 "video"
    extracted_text: str
    rewritten_text: str = ""
    final_text: str = ""          # 用户确认后的文本
    audio_path: Optional[str] = None
    video_url: Optional[str] = None


def make_workflow_store() -> Callable[[str], WorkflowState]:
    """
    返回一个 get_workflow(session_id) 函数，从内存字典中取状态。
    不存在时抛 KeyError，由调用方转换为 HTTP 404。
    """
    store: dict[str, WorkflowState] = {}

    def get_workflow(session_id: str) -> WorkflowState:
        if session_id not in store:
            raise KeyError(session_id)
        return store[session_id]

    # 将 store 绑定到函数上，供 create_workflow 使用
    get_workflow._store = store  # type: ignore[attr-defined]
    return get_workflow


def create_workflow(
    store_fn: Callable,
    source: str,
    source_type: str,
    extracted_text: str,
) -> WorkflowState:
    """创建一条新的工作流记录并保存。"""
    session_id = str(uuid.uuid4())
    state = WorkflowState(
        session_id=session_id,
        current_step=WorkflowStep.EXTRACTED,
        source=source,
        source_type=source_type,
        extracted_text=extracted_text,
    )
    store_fn._store[session_id] = state  # type: ignore[attr-defined]
    return state
