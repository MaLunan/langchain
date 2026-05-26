"""
可灵 AI 视频生成服务。

支持两种模式（公开函数在后续步骤中添加）：
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

import jwt
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
    now = int(time.time())
    payload = {"iss": ak, "exp": now + 1800, "nbf": now - 5}
    return jwt.encode(payload, sk, algorithm="HS256")


def _auth_headers(ak: str, sk: str) -> dict:
    """构建带 JWT 鉴权的请求头。"""
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
        if not isinstance(data, dict):
            raise RuntimeError(f"API 响应格式异常：{resp.text}")
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
