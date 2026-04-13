"""
本地 HTTP 接口：把 RAG + 多轮对话暴露成 REST，方便前端、其它服务或 curl 调用。

为什么用 FastAPI？
  自动生成 OpenAPI 文档、类型校验清晰，和 Pydantic 生态一致，适合快速搭本地/内网 API。

启动（项目根目录、已激活虚拟环境）：
  uvicorn server:app --host 127.0.0.1 --port 8000

局域网可访问（手机连同一 WiFi 调试时）：
  uvicorn server:app --host 0.0.0.0 --port 8000

浏览器打开接口说明：http://127.0.0.1:8000/docs

生产环境注意：公网务必加鉴权（API Key）、HTTPS（Nginx/Caddy）、限流与日志。
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from multi_agent import create_agent_hub, suggest_agent_for_message
from workflow_state import WorkflowStep, create_workflow, make_workflow_store

# 本地文件存储目录
_BASE_DIR = Path(__file__).resolve().parent
UPLOADS_DIR = _BASE_DIR / "uploads"
GENERATED_DIR = _BASE_DIR / "generated"
UPLOADS_DIR.mkdir(exist_ok=True)
GENERATED_DIR.mkdir(exist_ok=True)


class AgentInfo(BaseModel):
    agent_id: str
    display_name: str
    description: str


class ChatRequest(BaseModel):
    """单次对话：同一 session_id 在同一角色下保留多轮记忆。"""

    message: str = Field(..., min_length=1, description="用户当前输入")
    session_id: str = Field(
        default="default",
        min_length=1,
        max_length=256,
        description="会话标识，例如用户 ID 或浏览器生成的 UUID",
    )
    agent_id: str = Field(
        default="assistant",
        description="角色 ID，见 GET /agents；与 auto_route 同时为真时先自动再回退",
    )
    auto_route: bool = Field(
        default=False,
        description="为 true 时先多调一次 Kimi 选角，再让该角色回答（多一次费用）",
    )


class ChatResponse(BaseModel):
    reply: str
    agent_id: str = Field(description="本轮实际使用的角色 ID")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动时构建向量库与各角色链；向量与嵌入模型只加载一次。
    hub, llm = create_agent_hub()
    app.state.agent_hub = hub
    app.state.router_llm = llm
    # 工作流状态存储
    app.state.workflow_store = make_workflow_store()
    yield


app = FastAPI(title="Kimi RAG Chat & 数字人工作流", lifespan=lifespan)

_origins = [o.strip() for o in os.getenv("CORS_ALLOW_ORIGINS", "*").split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/agents", response_model=list[AgentInfo])
def list_agents(request: Request):
    """列出可用角色，供前端下拉框或调试。"""
    from multi_agent import BUILTIN_AGENT_PROFILES

    return [
        AgentInfo(agent_id=p.agent_id, display_name=p.display_name, description=p.description)
        for p in BUILTIN_AGENT_PROFILES
    ]


@app.post("/chat", response_model=ChatResponse)
def chat(body: ChatRequest, request: Request):
    hub = request.app.state.agent_hub
    llm = request.app.state.router_llm

    if body.auto_route:
        used_id = suggest_agent_for_message(body.message, llm)
    else:
        used_id = body.agent_id.strip() or "assistant"

    if used_id not in hub:
        raise HTTPException(
            status_code=400,
            detail=f"未知 agent_id：{used_id}，请先 GET /agents 查看列表。",
        )

    chain = hub[used_id]
    try:
        out = chain.invoke(
            {"input": body.message.strip()},
            config={"configurable": {"session_id": body.session_id}},
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
    return ChatResponse(reply=out.content or "", agent_id=used_id)


# ---------------------------------------------------------------------------
# 工作流：内容提取 → 文本改写 → 用户确认 → 音频 → 数字人视频
# ---------------------------------------------------------------------------

class WorkflowStartRequest(BaseModel):
    source: str = Field(..., description="网页 URL 或已上传视频文件的服务器路径")


class WorkflowStartResponse(BaseModel):
    session_id: str
    source_type: str
    extracted_text: str


class RewriteStyleInfo(BaseModel):
    style_id: str
    display_name: str


class RewriteRequest(BaseModel):
    style_id: str = Field(default="news", description="改写风格 ID，见 GET /rewrite-styles")


class RewriteResponse(BaseModel):
    session_id: str
    rewritten_text: str


class ConfirmRequest(BaseModel):
    final_text: str = Field(..., min_length=1, description="用户最终确认（或修改）的文本")


class ConfirmResponse(BaseModel):
    session_id: str
    final_text: str


class AudioResponse(BaseModel):
    session_id: str
    audio_url: str


class VideoResponse(BaseModel):
    session_id: str
    video_url: str


class WorkflowStatusResponse(BaseModel):
    session_id: str
    current_step: str
    source_type: str
    extracted_text: str
    rewritten_text: str
    final_text: str
    audio_url: str | None
    video_url: str | None


def _get_state(request: Request, session_id: str):
    """从 store 取状态，找不到抛 404。"""
    try:
        return request.app.state.workflow_store(session_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"工作流会话不存在：{session_id}")


@app.post("/workflow/start", response_model=WorkflowStartResponse, tags=["workflow"])
def workflow_start(body: WorkflowStartRequest, request: Request):
    """步骤 1：提交 URL 或本地视频路径，提取文本，返回 session_id。"""
    from content_extraction import extract_content

    try:
        text, source_type = extract_content(body.source)
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"内容提取失败：{e}") from e

    state = create_workflow(
        request.app.state.workflow_store,
        source=body.source,
        source_type=source_type,
        extracted_text=text,
    )
    return WorkflowStartResponse(
        session_id=state.session_id,
        source_type=state.source_type,
        extracted_text=state.extracted_text,
    )


@app.post("/workflow/upload", tags=["workflow"])
async def workflow_upload(file: UploadFile = File(...)):
    """上传视频文件到 uploads/ 目录，返回服务器文件路径，供 /workflow/start 使用。"""
    dest = UPLOADS_DIR / file.filename
    content = await file.read()
    dest.write_bytes(content)
    return {"file_path": str(dest)}


@app.get("/rewrite-styles", response_model=list[RewriteStyleInfo], tags=["workflow"])
def list_rewrite_styles():
    """查询可用改写风格。"""
    from text_rewrite import BUILTIN_REWRITE_STYLES

    return [
        RewriteStyleInfo(style_id=s.style_id, display_name=s.display_name)
        for s in BUILTIN_REWRITE_STYLES
    ]


@app.post("/workflow/{session_id}/rewrite", response_model=RewriteResponse, tags=["workflow"])
def workflow_rewrite(session_id: str, body: RewriteRequest, request: Request):
    """步骤 2：改写提取到的文本，返回改写结果。"""
    from text_rewrite import rewrite_text

    state = _get_state(request, session_id)
    if state.current_step == WorkflowStep.VIDEO_DONE:
        raise HTTPException(status_code=409, detail="工作流已完成，无法重新改写。")

    llm = request.app.state.router_llm
    try:
        rewritten = rewrite_text(state.extracted_text, body.style_id, llm)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"改写失败：{e}") from e

    state.rewritten_text = rewritten
    state.current_step = WorkflowStep.REWRITTEN
    return RewriteResponse(session_id=session_id, rewritten_text=rewritten)


@app.post("/workflow/{session_id}/confirm", response_model=ConfirmResponse, tags=["workflow"])
def workflow_confirm(session_id: str, body: ConfirmRequest, request: Request):
    """步骤 3：用户确认或修改文本，存入 final_text。"""
    state = _get_state(request, session_id)
    state.final_text = body.final_text.strip()
    state.current_step = WorkflowStep.CONFIRMED
    return ConfirmResponse(session_id=session_id, final_text=state.final_text)


@app.post("/workflow/{session_id}/audio", response_model=AudioResponse, tags=["workflow"])
def workflow_audio(session_id: str, request: Request):
    """步骤 4a：根据 final_text 生成 Edge TTS 音频，返回音频文件 URL。"""
    from tts_service import text_to_speech

    state = _get_state(request, session_id)
    if not state.final_text:
        raise HTTPException(status_code=409, detail="请先确认文本（POST /workflow/{id}/confirm）。")

    output_path = GENERATED_DIR / f"{session_id}.mp3"
    try:
        text_to_speech(state.final_text, output_path)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"TTS 生成失败：{e}") from e

    state.audio_path = str(output_path)
    state.current_step = WorkflowStep.AUDIO_DONE

    audio_url = f"/generated/{session_id}.mp3"
    return AudioResponse(session_id=session_id, audio_url=audio_url)


@app.post("/workflow/{session_id}/video", response_model=VideoResponse, tags=["workflow"])
def workflow_video(session_id: str, request: Request):
    """步骤 4b：调用火山引擎数字人 API 生成视频，返回视频 URL。"""
    from digital_human_service import generate_digital_human_video

    state = _get_state(request, session_id)
    if not state.audio_path:
        raise HTTPException(status_code=409, detail="请先生成音频（POST /workflow/{id}/audio）。")

    audio_path = Path(state.audio_path)
    if not audio_path.exists():
        raise HTTPException(status_code=500, detail=f"音频文件不存在：{audio_path}")

    try:
        video_url = generate_digital_human_video(audio_path)
    except EnvironmentError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"数字人视频生成失败：{e}") from e

    state.video_url = video_url
    state.current_step = WorkflowStep.VIDEO_DONE
    return VideoResponse(session_id=session_id, video_url=video_url)


@app.get("/workflow/{session_id}/status", response_model=WorkflowStatusResponse, tags=["workflow"])
def workflow_status(session_id: str, request: Request):
    """查询工作流整体状态。"""
    state = _get_state(request, session_id)
    return WorkflowStatusResponse(
        session_id=state.session_id,
        current_step=state.current_step.value,
        source_type=state.source_type,
        extracted_text=state.extracted_text,
        rewritten_text=state.rewritten_text,
        final_text=state.final_text,
        audio_url=f"/generated/{session_id}.mp3" if state.audio_path else None,
        video_url=state.video_url,
    )


# 挂载静态文件目录，让前端可以直接访问生成的音视频
app.mount("/generated", StaticFiles(directory=str(GENERATED_DIR)), name="generated")
