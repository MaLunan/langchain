from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Optional


class WorkflowStep(str, Enum):
    EXTRACTED     = "extracted"
    REWRITTEN     = "rewritten"
    CONFIRMED     = "confirmed"
    MODE_SELECTED = "mode_selected"
    AUDIO_DONE    = "audio_done"
    VIDEO_DONE    = "video_done"


@dataclass
class WorkflowState:
    session_id:     str
    current_step:   WorkflowStep
    source:         str
    source_type:    str
    extracted_text: str
    rewritten_text: str = ""
    final_text:     str = ""
    audio_path:     Optional[str] = None
    video_url:      Optional[str] = None
    video_mode:     str = ""          # "avatar" | "text2video"


def make_workflow_store() -> Callable[[str], WorkflowState]:
    store: dict[str, WorkflowState] = {}

    def get_workflow(session_id: str) -> WorkflowState:
        if session_id not in store:
            raise KeyError(session_id)
        return store[session_id]

    get_workflow._store = store  # type: ignore[attr-defined]
    return get_workflow


def create_workflow(
    store_fn: Callable,
    source: str,
    source_type: str,
    extracted_text: str,
) -> WorkflowState:
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
