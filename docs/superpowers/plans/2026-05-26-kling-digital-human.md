# 可灵 AI 数字人 / 文生视频集成 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将数字人视频生成服务从火山引擎切换至可灵 AI，并新增「文生视频」模式，让用户在确认文本后选择走哪条路径。

**Architecture:** 新增 `kling_service.py` 封装 JWT 鉴权 + 两种可灵 API 调用；`workflow_state.py` 加一个字段；`server.py` 的 `/video` 路由接受 `mode` 参数；前端在「确认文本」之后插入模式选择步骤，Mode B 跳过音频步骤直达视频生成。

**Tech Stack:** Python 3.10+, PyJWT, requests, FastAPI, Vue 3 Composition API

---

## 文件清单

| 动作 | 路径 | 说明 |
|---|---|---|
| 新建 | `kling_service.py` | 可灵 API 封装：JWT + avatar + text2video |
| 新建 | `tests/test_kling_service.py` | 单元测试（mock requests） |
| 修改 | `workflow_state.py` | 新增 `video_mode` 字段 + `MODE_SELECTED` 步骤 |
| 修改 | `server.py:179-182,299-321` | 新增 `VideoRequest` 模型；更新 `/video` 路由 |
| 修改 | `frontend/src/api/workflow.js:55-57` | 更新 `generateVideo` 签名 |
| 修改 | `frontend/src/App.vue` | 插入模式选择步骤，Mode B 跳过音频 |
| 修改 | `pyproject.toml` | 新增 `PyJWT` 依赖 |

---

## Task 1: kling_service.py — JWT 鉴权 + 公共轮询

**Files:**
- Create: `kling_service.py`
- Create: `tests/test_kling_service.py`

- [ ] **Step 1: 写失败测试**

新建 `tests/test_kling_service.py`：

```python
"""可灵 service 单元测试（全部 mock，不发真实 HTTP）"""
import os
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ── JWT 鉴权 ────────────────────────────────────────────────────────────────

def test_make_jwt_contains_iss():
    from kling_service import _make_jwt
    token = _make_jwt("ak_test", "sk_test")
    import jwt as pyjwt
    payload = pyjwt.decode(token, "sk_test", algorithms=["HS256"])
    assert payload["iss"] == "ak_test"
    assert payload["exp"] > int(time.time())


# ── 轮询 ────────────────────────────────────────────────────────────────────

def test_poll_task_returns_url_on_succeed():
    from kling_service import _poll_task
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {
        "data": {"status": "succeed", "video_url": "https://example.com/v.mp4"}
    }
    with patch("kling_service.requests.get", return_value=mock_resp):
        with patch("kling_service._make_jwt", return_value="tok"):
            url = _poll_task("task_abc", timeout=10)
    assert url == "https://example.com/v.mp4"


def test_poll_task_raises_on_failed():
    from kling_service import _poll_task
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {"data": {"status": "failed"}}
    with patch("kling_service.requests.get", return_value=mock_resp):
        with patch("kling_service._make_jwt", return_value="tok"):
            with pytest.raises(RuntimeError, match="任务.*失败"):
                _poll_task("task_xyz", timeout=10)
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
uv run pytest tests/test_kling_service.py -v
```

预期：`ModuleNotFoundError: No module named 'kling_service'`

- [ ] **Step 3: 添加 PyJWT 依赖**

在 `pyproject.toml` 的 `dependencies` 中添加：

```toml
"PyJWT>=2.8.0",
```

然后安装：

```bash
uv sync
```

- [ ] **Step 4: 实现 `kling_service.py`（JWT + 轮询部分）**

新建 `kling_service.py`：

```python
"""
可灵 AI 视频生成服务。

支持两种模式：
  A. 数字人口播：音频 → 数字人对嘴视频（generate_avatar_video）
  B. 文生视频：  文字 → AI 生成视频   （generate_text_to_video）

鉴权：JWT HS256，每次请求前动态签发（有效期 30 分钟）。

环境变量：
  KLING_ACCESS_KEY_ID       可灵 Access Key ID
  KLING_ACCESS_KEY_SECRET   可灵 Access Key Secret
  KLING_AVATAR_ID           数字人形象 ID（模式 A 使用）
"""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Optional

import requests

_BASE_URL = "https://api.klingai.com"


# ── 鉴权 ──────────────────────────────────────────────────────────────────

def _get_credentials() -> tuple[str, str]:
    ak = os.getenv("KLING_ACCESS_KEY_ID", "").strip()
    sk = os.getenv("KLING_ACCESS_KEY_SECRET", "").strip()
    if not ak or not sk:
        raise EnvironmentError(
            "请在 .env 中设置 KLING_ACCESS_KEY_ID 和 KLING_ACCESS_KEY_SECRET"
        )
    return ak, sk


def _make_jwt(ak: str, sk: str) -> str:
    """签发 JWT，有效期 30 分钟。"""
    import jwt

    now = int(time.time())
    payload = {"iss": ak, "exp": now + 1800, "nbf": now - 5}
    return jwt.encode(payload, sk, algorithm="HS256")


def _auth_headers(ak: str, sk: str) -> dict:
    return {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {_make_jwt(ak, sk)}",
    }


# ── 公共轮询 ──────────────────────────────────────────────────────────────

def _poll_task(task_id: str, timeout: int = 300) -> str:
    """
    轮询 GET /v1/videos/{task_id}，直到 status=succeed 或超时。

    返回视频 URL。
    """
    ak, sk = _get_credentials()
    url = f"{_BASE_URL}/v1/videos/{task_id}"
    deadline = time.time() + timeout

    while time.time() < deadline:
        resp = requests.get(url, headers=_auth_headers(ak, sk), timeout=30)
        resp.raise_for_status()
        data = resp.json().get("data", {})
        status = data.get("status", "")

        if status == "succeed":
            video_url = data.get("video_url", "")
            if not video_url:
                raise RuntimeError(f"任务完成但无视频 URL：{resp.text}")
            return video_url
        if status in ("failed", "cancelled"):
            raise RuntimeError(f"任务 {task_id} 失败，状态：{status}")

        time.sleep(5)

    raise TimeoutError(f"轮询超时（{timeout}s），task_id={task_id}")
```

- [ ] **Step 5: 运行测试，确认通过**

```bash
uv run pytest tests/test_kling_service.py::test_make_jwt_contains_iss tests/test_kling_service.py::test_poll_task_returns_url_on_succeed tests/test_kling_service.py::test_poll_task_raises_on_failed -v
```

预期：3 PASSED

- [ ] **Step 6: 提交**

```bash
git add kling_service.py tests/test_kling_service.py pyproject.toml uv.lock
git commit -m "feat: add kling_service JWT auth and task polling"
```

---

## Task 2: kling_service.py — 数字人口播（Mode A）

**Files:**
- Modify: `kling_service.py`
- Modify: `tests/test_kling_service.py`

- [ ] **Step 1: 写失败测试**

在 `tests/test_kling_service.py` 末尾追加：

```python
# ── 数字人口播 ───────────────────────────────────────────────────────────────

def test_generate_avatar_video_calls_lip_sync(tmp_path):
    from kling_service import generate_avatar_video

    # 建一个假音频文件
    audio = tmp_path / "test.mp3"
    audio.write_bytes(b"fake_audio")

    post_resp = MagicMock()
    post_resp.raise_for_status = MagicMock()
    post_resp.json.return_value = {"data": {"task_id": "avatar_task_1"}}

    poll_resp = MagicMock()
    poll_resp.raise_for_status = MagicMock()
    poll_resp.json.return_value = {
        "data": {"status": "succeed", "video_url": "https://cdn.kling.ai/avatar.mp4"}
    }

    with patch("kling_service.requests.post", return_value=post_resp), \
         patch("kling_service.requests.get", return_value=poll_resp), \
         patch("kling_service._make_jwt", return_value="tok"), \
         patch.dict(os.environ, {"KLING_ACCESS_KEY_ID": "ak", "KLING_ACCESS_KEY_SECRET": "sk",
                                  "KLING_AVATAR_ID": "avatar_001"}):
        url = generate_avatar_video(audio)

    assert url == "https://cdn.kling.ai/avatar.mp4"
    # 验证调用了 lip-sync 接口
    call_url = kling_service_requests_post_url(post_resp)  # 下方 helper
```

> 注：上面最后一行是辅助说明用，实际测试不用 helper，直接用 mock 的 `call_args`：

```python
def test_generate_avatar_video_calls_lip_sync(tmp_path):
    from kling_service import generate_avatar_video

    audio = tmp_path / "test.mp3"
    audio.write_bytes(b"fake_audio")

    post_resp = MagicMock()
    post_resp.raise_for_status = MagicMock()
    post_resp.json.return_value = {"data": {"task_id": "avatar_task_1"}}

    poll_resp = MagicMock()
    poll_resp.raise_for_status = MagicMock()
    poll_resp.json.return_value = {
        "data": {"status": "succeed", "video_url": "https://cdn.kling.ai/avatar.mp4"}
    }

    with patch("kling_service.requests.post", return_value=post_resp) as mock_post, \
         patch("kling_service.requests.get", return_value=poll_resp), \
         patch("kling_service._make_jwt", return_value="tok"), \
         patch.dict(os.environ, {"KLING_ACCESS_KEY_ID": "ak", "KLING_ACCESS_KEY_SECRET": "sk",
                                  "KLING_AVATAR_ID": "avatar_001"}):
        url = generate_avatar_video(audio)

    assert url == "https://cdn.kling.ai/avatar.mp4"
    assert "lip-sync" in mock_post.call_args[0][0]
```

- [ ] **Step 2: 运行，确认失败**

```bash
uv run pytest tests/test_kling_service.py::test_generate_avatar_video_calls_lip_sync -v
```

预期：FAILED — `ImportError` 或 `AttributeError`

- [ ] **Step 3: 实现 `generate_avatar_video`**

在 `kling_service.py` 末尾追加：

```python
# ── 模式 A：数字人口播 ─────────────────────────────────────────────────────

def generate_avatar_video(
    audio_path: Path,
    avatar_id: Optional[str] = None,
    timeout: int = 300,
) -> str:
    """
    上传音频至可灵，生成数字人口播视频。

    avatar_id 默认读取环境变量 KLING_AVATAR_ID。
    返回可访问的视频 URL。
    """
    ak, sk = _get_credentials()
    if avatar_id is None:
        avatar_id = os.getenv("KLING_AVATAR_ID", "").strip()
    if not avatar_id:
        raise ValueError("未配置 KLING_AVATAR_ID，或未传入 avatar_id")

    # Step 1: 上传音频，获取 audio_url
    upload_url = f"{_BASE_URL}/v1/audios"
    with open(audio_path, "rb") as f:
        upload_resp = requests.post(
            upload_url,
            headers={"Authorization": f"Bearer {_make_jwt(ak, sk)}"},
            files={"file": (audio_path.name, f, "audio/mpeg")},
            timeout=60,
        )
    upload_resp.raise_for_status()
    audio_url = upload_resp.json().get("data", {}).get("url", "")
    if not audio_url:
        raise RuntimeError(f"音频上传失败：{upload_resp.text}")

    # Step 2: 提交 lip-sync 任务
    task_resp = requests.post(
        f"{_BASE_URL}/v1/videos/lip-sync",
        headers=_auth_headers(ak, sk),
        json={"avatar_id": avatar_id, "audio_url": audio_url},
        timeout=30,
    )
    task_resp.raise_for_status()
    task_id = task_resp.json().get("data", {}).get("task_id", "")
    if not task_id:
        raise RuntimeError(f"任务提交失败：{task_resp.text}")

    return _poll_task(task_id, timeout=timeout)
```

- [ ] **Step 4: 运行测试**

```bash
uv run pytest tests/test_kling_service.py::test_generate_avatar_video_calls_lip_sync -v
```

预期：PASSED

- [ ] **Step 5: 提交**

```bash
git add kling_service.py tests/test_kling_service.py
git commit -m "feat: kling_service Mode A — avatar lip-sync video"
```

---

## Task 3: kling_service.py — 文生视频（Mode B）

**Files:**
- Modify: `kling_service.py`
- Modify: `tests/test_kling_service.py`

- [ ] **Step 1: 写失败测试**

在 `tests/test_kling_service.py` 末尾追加：

```python
# ── 文生视频 ─────────────────────────────────────────────────────────────────

def test_generate_text_to_video_submits_prompt(tmp_path):
    from kling_service import generate_text_to_video

    post_resp = MagicMock()
    post_resp.raise_for_status = MagicMock()
    post_resp.json.return_value = {"data": {"task_id": "t2v_task_1"}}

    poll_resp = MagicMock()
    poll_resp.raise_for_status = MagicMock()
    poll_resp.json.return_value = {
        "data": {"status": "succeed", "video_url": "https://cdn.kling.ai/t2v.mp4"}
    }

    with patch("kling_service.requests.post", return_value=post_resp) as mock_post, \
         patch("kling_service.requests.get", return_value=poll_resp), \
         patch("kling_service._make_jwt", return_value="tok"), \
         patch.dict(os.environ, {"KLING_ACCESS_KEY_ID": "ak", "KLING_ACCESS_KEY_SECRET": "sk"}):
        url = generate_text_to_video("一段科技感十足的介绍视频")

    assert url == "https://cdn.kling.ai/t2v.mp4"
    body = mock_post.call_args[1]["json"]
    assert body["prompt"] == "一段科技感十足的介绍视频"
    assert body["duration"] == 5
    assert body["aspect_ratio"] == "16:9"
```

- [ ] **Step 2: 运行，确认失败**

```bash
uv run pytest tests/test_kling_service.py::test_generate_text_to_video_submits_prompt -v
```

预期：FAILED

- [ ] **Step 3: 实现 `generate_text_to_video`**

在 `kling_service.py` 末尾追加：

```python
# ── 模式 B：文生视频 ───────────────────────────────────────────────────────

def generate_text_to_video(
    text: str,
    model: str = "kling-v1",
    duration: int = 5,
    aspect_ratio: str = "16:9",
    mode: str = "std",
    timeout: int = 300,
) -> str:
    """
    将文字描述提交给可灵文生视频接口，轮询等待，返回视频 URL。

    model:        "kling-v1" 或 "kling-v1-5"
    duration:     5 或 10（秒）
    aspect_ratio: "16:9" / "9:16" / "1:1"
    mode:         "std"（标准）或 "pro"（高质量，消耗更多配额）
    """
    ak, sk = _get_credentials()

    payload = {
        "model": model,
        "prompt": text,
        "duration": duration,
        "aspect_ratio": aspect_ratio,
        "mode": mode,
    }
    resp = requests.post(
        f"{_BASE_URL}/v1/videos/text2video",
        headers=_auth_headers(ak, sk),
        json=payload,
        timeout=30,
    )
    resp.raise_for_status()
    task_id = resp.json().get("data", {}).get("task_id", "")
    if not task_id:
        raise RuntimeError(f"文生视频任务提交失败：{resp.text}")

    return _poll_task(task_id, timeout=timeout)
```

- [ ] **Step 4: 运行全部测试**

```bash
uv run pytest tests/test_kling_service.py -v
```

预期：全部 PASSED

- [ ] **Step 5: 提交**

```bash
git add kling_service.py tests/test_kling_service.py
git commit -m "feat: kling_service Mode B — text-to-video"
```

---

## Task 4: workflow_state.py — 新增 video_mode + MODE_SELECTED

**Files:**
- Modify: `workflow_state.py`

- [ ] **Step 1: 修改 `workflow_state.py`**

```python
# workflow_state.py 完整替换

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Optional


class WorkflowStep(str, Enum):
    EXTRACTED     = "extracted"
    REWRITTEN     = "rewritten"
    CONFIRMED     = "confirmed"
    MODE_SELECTED = "mode_selected"   # ← 新增
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
    video_mode:     str = ""          # ← 新增："avatar" | "text2video"


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
```

- [ ] **Step 2: 验证服务器仍能启动**

```bash
uv run python -c "from workflow_state import WorkflowStep, WorkflowState; print('OK')"
```

预期：`OK`

- [ ] **Step 3: 提交**

```bash
git add workflow_state.py
git commit -m "feat: workflow_state adds video_mode field and MODE_SELECTED step"
```

---

## Task 5: server.py — /video 路由支持 mode 参数

**Files:**
- Modify: `server.py`

- [ ] **Step 1: 在 `server.py` 的 Pydantic 模型区域（第 179 行附近）添加 `VideoRequest`**

在 `VideoResponse` 类定义之后（第 182 行后）插入：

```python
class VideoRequest(BaseModel):
    mode: str = Field(
        ...,
        description="生成模式：avatar（数字人口播）或 text2video（文生视频）",
        pattern="^(avatar|text2video)$",
    )
```

- [ ] **Step 2: 更新 `/workflow/{id}/video` 路由**

将原来的 `workflow_video` 函数（第 299–321 行）替换为：

```python
@app.post("/workflow/{session_id}/video", response_model=VideoResponse, tags=["workflow"])
def workflow_video(session_id: str, body: VideoRequest, request: Request):
    """
    步骤 5：生成视频。

    mode=avatar    先必须调用 /audio，用音频驱动数字人口播（可灵 lip-sync）。
    mode=text2video 直接用 final_text 调用可灵文生视频，无需先生成音频。
    """
    from kling_service import generate_avatar_video, generate_text_to_video

    state = _get_state(request, session_id)

    if body.mode == "avatar":
        if not state.audio_path:
            raise HTTPException(
                status_code=409,
                detail="mode=avatar 需要先生成音频（POST /workflow/{id}/audio）。",
            )
        audio_path = Path(state.audio_path)
        if not audio_path.exists():
            raise HTTPException(status_code=500, detail=f"音频文件不存在：{audio_path}")
        try:
            video_url = generate_avatar_video(audio_path)
        except EnvironmentError as e:
            raise HTTPException(status_code=503, detail=str(e)) from e
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"数字人视频生成失败：{e}") from e

    else:  # text2video
        if not state.final_text:
            raise HTTPException(
                status_code=409,
                detail="请先确认文本（POST /workflow/{id}/confirm）。",
            )
        try:
            video_url = generate_text_to_video(state.final_text)
        except EnvironmentError as e:
            raise HTTPException(status_code=503, detail=str(e)) from e
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"文生视频生成失败：{e}") from e

    state.video_mode = body.mode
    state.video_url = video_url
    state.current_step = WorkflowStep.VIDEO_DONE
    return VideoResponse(session_id=session_id, video_url=video_url)
```

- [ ] **Step 3: 验证 server 语法**

```bash
uv run python -c "import server; print('OK')"
```

预期：`OK`

- [ ] **Step 4: 提交**

```bash
git add server.py
git commit -m "feat: server /video route accepts mode=avatar|text2video"
```

---

## Task 6: frontend/src/api/workflow.js — 更新 generateVideo

**Files:**
- Modify: `frontend/src/api/workflow.js`

- [ ] **Step 1: 更新 `generateVideo` 函数**

将第 54–57 行替换为：

```js
/** 步骤 5：生成视频
 * @param {string} sessionId
 * @param {'avatar'|'text2video'} mode
 * @param {object} params  文生视频额外参数（duration、aspect_ratio、model）
 */
export async function generateVideo(sessionId, mode, params = {}) {
  return request('POST', `/workflow/${sessionId}/video`, { mode, ...params })
}
```

- [ ] **Step 2: 确认无语法错误**

```bash
cd frontend && node --input-type=module < src/api/workflow.js 2>&1 | head -5; cd ..
```

预期：无报错（若有 `fetch is not defined` 是正常的，说明语法没问题）

- [ ] **Step 3: 提交**

```bash
git add frontend/src/api/workflow.js
git commit -m "feat: workflow.js generateVideo accepts mode param"
```

---

## Task 7: 前端 — 插入模式选择步骤

**Files:**
- Modify: `frontend/src/App.vue`

- [ ] **Step 1: 更新步骤定义和状态变量**

在 `<script setup>` 中找到 `const STEPS = [...]`（第 261 行）并替换为：

```js
const STEPS = [
  { key: 'extract', label: '提取内容' },
  { key: 'rewrite', label: 'AI 改写' },
  { key: 'confirm', label: '确认文本' },
  { key: 'mode',    label: '选择模式' },   // 新增，index=3
  { key: 'audio',   label: '生成语音' },   // index=4，Mode B 时跳过
  { key: 'video',   label: '生成视频' },   // index=5
]
```

在响应式状态区域（`const videoUrl = ref('')` 之后）新增：

```js
const videoMode = ref('')   // 'avatar' | 'text2video'
const t2vDuration    = ref(5)
const t2vAspectRatio = ref('16:9')
```

- [ ] **Step 2: 替换步骤 3 面板（原"生成语音"变为"选择模式"）**

找到 `<!-- ── 步骤 3：生成音频 ──────────────────────────── -->` 部分（第 168–201 行），替换为以下两个面板：

```html
<!-- ── 步骤 3：选择模式 ──────────────────────────── -->
<div v-if="currentStep === 3" class="card">
  <div class="card-title">
    <span>🎯 选择生成方式</span>
    <span class="badge">步骤 4</span>
  </div>

  <div class="mode-grid">
    <div
      class="mode-card"
      :class="{ selected: videoMode === 'avatar' }"
      @click="videoMode = 'avatar'"
    >
      <div class="mode-icon">🎙️</div>
      <div class="mode-title">数字人口播</div>
      <div class="mode-desc">生成 TTS 音频，再驱动数字人对嘴播报</div>
    </div>
    <div
      class="mode-card"
      :class="{ selected: videoMode === 'text2video' }"
      @click="videoMode = 'text2video'"
    >
      <div class="mode-icon">🎬</div>
      <div class="mode-title">文生视频</div>
      <div class="mode-desc">直接将文字交给可灵 AI 生成视频，无需音频</div>
    </div>
  </div>

  <!-- 文生视频参数（仅 text2video 时显示） -->
  <template v-if="videoMode === 'text2video'">
    <div class="input-group" style="margin-top:16px">
      <label>视频时长</label>
      <div class="tabs" style="width:fit-content">
        <button class="tab-btn" :class="{ active: t2vDuration === 5 }" @click="t2vDuration = 5">5 秒</button>
        <button class="tab-btn" :class="{ active: t2vDuration === 10 }" @click="t2vDuration = 10">10 秒</button>
      </div>
    </div>
    <div class="input-group">
      <label>画面比例</label>
      <div class="tabs" style="width:fit-content">
        <button class="tab-btn" :class="{ active: t2vAspectRatio === '16:9' }" @click="t2vAspectRatio = '16:9'">16:9</button>
        <button class="tab-btn" :class="{ active: t2vAspectRatio === '9:16' }" @click="t2vAspectRatio = '9:16'">9:16</button>
        <button class="tab-btn" :class="{ active: t2vAspectRatio === '1:1' }" @click="t2vAspectRatio = '1:1'">1:1</button>
      </div>
    </div>
  </template>

  <div class="btn-row">
    <button class="btn btn-outline" @click="currentStep = 2">← 修改文本</button>
    <button
      class="btn btn-primary"
      :disabled="!videoMode"
      @click="handleModeSelect"
    >
      下一步 →
    </button>
  </div>
</div>

<!-- ── 步骤 4：生成音频（仅 Mode A）───────────────── -->
<div v-if="currentStep === 4" class="card">
  <div class="card-title">
    <span>🔊 生成语音</span>
    <span class="badge">步骤 5</span>
  </div>

  <div class="input-group">
    <label>待播报文本</label>
    <div class="result-box">{{ finalText }}</div>
  </div>

  <template v-if="audioUrl">
    <div class="alert alert-success">✅ 音频生成成功</div>
    <audio :src="audioUrl" controls></audio>
  </template>

  <div class="btn-row">
    <button class="btn btn-outline" @click="currentStep = 3">← 重新选择</button>
    <button v-if="!audioUrl" class="btn btn-primary" :disabled="loading" @click="handleAudio">
      <span v-if="loading" class="spinner"></span>
      <span>{{ loading ? '生成中…' : '生成语音' }}</span>
    </button>
    <button v-if="audioUrl" class="btn btn-primary" @click="currentStep = 5">
      下一步：生成视频 →
    </button>
  </div>
</div>
```

- [ ] **Step 3: 更新步骤 4（原步骤 4）→ 步骤 5**

找到 `<!-- ── 步骤 4：生成数字人视频 ───────────────────── -->` 部分（第 203 行），将 `v-if="currentStep === 4"` 改为 `v-if="currentStep === 5"`，badge 文字改为"步骤 6"，内容如下替换：

```html
<!-- ── 步骤 5：生成视频 ───────────────────────────── -->
<div v-if="currentStep === 5" class="card">
  <div class="card-title">
    <span>{{ videoMode === 'avatar' ? '🤖 数字人视频' : '🎬 文生视频' }}</span>
    <span class="badge">步骤 6</span>
  </div>

  <template v-if="videoUrl">
    <div class="alert alert-success">🎉 视频生成成功！</div>
    <a :href="videoUrl" target="_blank" class="video-link">🎬 点击查看 / 下载视频</a>
  </template>
  <template v-else>
    <div class="alert alert-info">
      ⚡ {{ videoMode === 'avatar' ? '数字人口播' : '文生视频' }}生成通常需要 1-3 分钟，请耐心等待。
    </div>
    <div v-if="videoMode === 'text2video'" class="alert alert-info" style="margin-top:0">
      📝 时长：{{ t2vDuration }}s　比例：{{ t2vAspectRatio }}
    </div>
    <div class="alert alert-info" style="margin-top:0">
      ⚙️ 需要在 .env 中配置 KLING_ACCESS_KEY_ID / KLING_ACCESS_KEY_SECRET{{ videoMode === 'avatar' ? ' / KLING_AVATAR_ID' : '' }}
    </div>
  </template>

  <div class="btn-row">
    <button class="btn btn-outline" @click="currentStep = videoMode === 'avatar' ? 4 : 3">← 返回</button>
    <button v-if="!videoUrl" class="btn btn-primary" :disabled="loading" @click="handleVideo">
      <span v-if="loading" class="spinner"></span>
      <span>{{ loading ? '生成中（请等待）…' : (videoMode === 'avatar' ? '生成数字人视频' : '文生视频') }}</span>
    </button>
    <button v-if="videoUrl" class="btn btn-success" @click="reset">🔄 重新开始</button>
  </div>
</div>
```

- [ ] **Step 4: 更新 `<script setup>` 中的函数**

在 `handleConfirm` 函数之后（约第 353 行后）新增 `handleModeSelect`：

```js
function handleModeSelect() {
  if (videoMode.value === 'avatar') {
    currentStep.value = 4   // 去生成音频
  } else {
    currentStep.value = 5   // 跳过音频，直接生成视频
  }
}
```

将原 `handleAudio` 中 `currentStep.value = 4` → 保持不动（音频成功后用户点"下一步"按钮跳到 5）。

将 `handleVideo` 函数替换为：

```js
async function handleVideo() {
  error.value = ''
  loading.value = true
  try {
    const params = videoMode.value === 'text2video'
      ? { duration: t2vDuration.value, aspect_ratio: t2vAspectRatio.value }
      : {}
    const res = await generateVideo(sessionId.value, videoMode.value, params)
    videoUrl.value = res.video_url
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}
```

将 `reset` 函数中补充重置新增状态：

```js
function reset() {
  currentStep.value   = 0
  sessionId.value     = ''
  urlInput.value      = ''
  selectedFile.value  = null
  extractedText.value = ''
  editableText.value  = ''
  finalText.value     = ''
  audioUrl.value      = ''
  videoUrl.value      = ''
  videoMode.value     = ''
  t2vDuration.value   = 5
  t2vAspectRatio.value = '16:9'
  error.value         = ''
}
```

- [ ] **Step 5: 在 `<style>` 区域新增 mode-card 样式**

在现有 `.style-card` 相关样式附近追加：

```css
.mode-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
  margin: 16px 0;
}
.mode-card {
  border: 2px solid #e5e7eb;
  border-radius: 12px;
  padding: 24px 16px;
  text-align: center;
  cursor: pointer;
  transition: border-color 0.2s, background 0.2s;
}
.mode-card:hover { border-color: #6366f1; }
.mode-card.selected { border-color: #6366f1; background: #f0f0ff; }
.mode-icon { font-size: 32px; margin-bottom: 8px; }
.mode-title { font-weight: 700; font-size: 15px; margin-bottom: 4px; }
.mode-desc { font-size: 12px; color: #888; line-height: 1.5; }
```

- [ ] **Step 6: 更新步骤指示器中对 `currentStep > i` 的跳步处理**

步骤指示器当前仅靠数字比大小判断完成态，Mode B 跳过步骤 4（音频）时步骤指示器会显示步骤 4 未完成。在步骤数组旁新增一个计算辅助：

```js
// 判断某步骤是否"已完成或被跳过"
function isStepDone(i) {
  if (currentStep.value > i) return true
  // Mode B 时音频步骤（index=4）标记为跳过
  if (i === 4 && videoMode.value === 'text2video' && currentStep.value >= 5) return true
  return false
}
```

将步骤指示器中的 `:class="{ done: currentStep > i }"` 改为 `:class="{ done: isStepDone(i) }"`。

- [ ] **Step 7: 验证前端可编译**

```bash
cd frontend && npm run build 2>&1 | tail -10; cd ..
```

预期：`built in Xs`，无 ERROR

- [ ] **Step 8: 提交**

```bash
git add frontend/src/App.vue
git commit -m "feat: frontend adds mode-select step and text2video support"
```

---

## Task 8: 环境变量文档 + 收尾

**Files:**
- Modify: `.env`（用户自己填），新建 `.env.example`

- [ ] **Step 1: 创建 `.env.example`**

```bash
cat > .env.example << 'EOF'
# Moonshot / Kimi
MOONSHOT_API_KEY=
MOONSHOT_MODEL=kimi-k2.5

# TTS
TTS_VOICE=zh-CN-XiaoxiaoNeural

# 可灵 AI（数字人 + 文生视频）
KLING_ACCESS_KEY_ID=
KLING_ACCESS_KEY_SECRET=
KLING_AVATAR_ID=          # 数字人口播模式需要，在可灵控制台创建形象后获取

# Volcengine（已废弃，保留备用）
# VOLCENGINE_ACCESS_KEY=
# VOLCENGINE_SECRET_KEY=
# VOLCENGINE_AVATAR_ID=
EOF
```

- [ ] **Step 2: 运行全部测试**

```bash
uv run pytest tests/ -v
```

预期：全部 PASSED

- [ ] **Step 3: 启动后端验证接口文档**

```bash
uv run uvicorn server:app --host 127.0.0.1 --port 8000 &
sleep 3
curl -s http://127.0.0.1:8000/openapi.json | python3 -c "import json,sys; paths=json.load(sys.stdin)['paths']; [print(p) for p in paths if 'video' in p]"
kill %1
```

预期：打印出 `/workflow/{session_id}/video`

- [ ] **Step 4: 最终提交**

```bash
git add .env.example
git commit -m "chore: add .env.example with kling AI config"
```

---

## 注意事项

1. **可灵 API 端点对齐**：`/v1/videos/lip-sync` 和 `/v1/videos/text2video` 是根据文档推断，首次运行前请对照 [可灵 API 文档](https://klingai.com/document-api/apiReference/model/avatar) 确认实际路径，若不符只需修改 `kling_service.py` 中的两个 URL 常量。

2. **音频上传接口**：`/v1/audios` 为推断，若可灵数字人接口直接接受 `audio_url`（已有外链），可跳过上传步骤，将 `audio_path` 改为直接传本地路径或先上传到 OSS。

3. **`digital_human_service.py`**：保留，不删除，但不再被调用。
