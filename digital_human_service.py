"""
火山引擎数字人视频生成服务。

文档参考：https://www.volcengine.com/docs/6791/
需要在 .env 中配置：
  VOLCENGINE_ACCESS_KEY、VOLCENGINE_SECRET_KEY、VOLCENGINE_AVATAR_ID

调用流程：
  1. submit_video_task()   ——  提交任务，获取 task_id
  2. poll_video_task()     ——  轮询状态，等待完成，返回视频 URL
  3. generate_digital_human_video()  ——  封装上两步
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class DigitalHumanConfig:
    """数字人任务配置，所有字段均可从环境变量读取默认值。"""

    avatar_id: str = field(
        default_factory=lambda: os.getenv("VOLCENGINE_AVATAR_ID", "")
    )
    region: str = field(
        default_factory=lambda: os.getenv("VOLCENGINE_REGION", "cn-north-1")
    )
    resolution: str = "1080p"       # 视频分辨率
    background_color: str = "#FFFFFF"


def _get_credentials() -> tuple[str, str]:
    """从环境变量读取火山引擎 AK/SK，缺失时抛 EnvironmentError。"""
    ak = os.getenv("VOLCENGINE_ACCESS_KEY", "").strip()
    sk = os.getenv("VOLCENGINE_SECRET_KEY", "").strip()
    if not ak or not sk:
        raise EnvironmentError(
            "请在 .env 中设置 VOLCENGINE_ACCESS_KEY 和 VOLCENGINE_SECRET_KEY"
        )
    return ak, sk


def _sign_request(method: str, path: str, body: dict, ak: str, sk: str) -> dict:
    """
    构造火山引擎 API 的签名请求头（V4 签名简化版）。

    正式生产请使用火山引擎官方 SDK（volcengine-python-sdk），
    这里提供一个轻量实现便于演示。
    """
    import requests

    timestamp = str(int(time.time()))
    body_str = json.dumps(body, ensure_ascii=False, separators=(",", ":"))
    body_hash = hashlib.sha256(body_str.encode()).hexdigest()

    sign_str = "\n".join([method, path, timestamp, body_hash])
    signature = hmac.new(sk.encode(), sign_str.encode(), hashlib.sha256).hexdigest()

    return {
        "Content-Type": "application/json",
        "X-Date": timestamp,
        "Authorization": f"HMAC-SHA256 AccessKeyId={ak}, Signature={signature}",
    }


def submit_video_task(audio_path: Path, config: DigitalHumanConfig) -> str:
    """
    上传音频并向火山引擎数字人 API 提交视频生成任务。

    返回 task_id（字符串）。
    """
    import requests

    ak, sk = _get_credentials()

    if not config.avatar_id:
        raise ValueError("DigitalHumanConfig.avatar_id 不能为空，请检查 VOLCENGINE_AVATAR_ID")

    base_url = f"https://visual.volcengineapi.com"

    # 1) 上传音频文件（multipart）
    upload_url = f"{base_url}/v1/audio/upload"
    with open(audio_path, "rb") as f:
        upload_resp = requests.post(
            upload_url,
            headers={"AccessKeyId": ak, "SecretAccessKey": sk},
            files={"file": (audio_path.name, f, "audio/mpeg")},
            timeout=60,
        )
    upload_resp.raise_for_status()
    audio_url = upload_resp.json().get("data", {}).get("url", "")
    if not audio_url:
        raise RuntimeError(f"音频上传失败：{upload_resp.text}")

    # 2) 提交数字人视频任务
    task_url = f"{base_url}/v1/digital_human/video/task"
    payload = {
        "avatar_id": config.avatar_id,
        "audio_url": audio_url,
        "resolution": config.resolution,
        "background_color": config.background_color,
    }
    headers = _sign_request("POST", "/v1/digital_human/video/task", payload, ak, sk)
    task_resp = requests.post(task_url, headers=headers, json=payload, timeout=30)
    task_resp.raise_for_status()

    task_id = task_resp.json().get("data", {}).get("task_id", "")
    if not task_id:
        raise RuntimeError(f"任务提交失败：{task_resp.text}")
    return task_id


def poll_video_task(task_id: str, timeout: int = 300) -> str:
    """
    轮询视频任务状态，直到完成或超时。

    返回视频 URL（字符串）。
    """
    import requests

    ak, sk = _get_credentials()
    base_url = "https://visual.volcengineapi.com"
    query_url = f"{base_url}/v1/digital_human/video/task/{task_id}"

    deadline = time.time() + timeout
    interval = 5  # 每 5 秒轮询一次

    while time.time() < deadline:
        resp = requests.get(
            query_url,
            headers={"AccessKeyId": ak, "SecretAccessKey": sk},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json().get("data", {})
        status = data.get("status", "")

        if status == "succeeded":
            video_url = data.get("video_url", "")
            if not video_url:
                raise RuntimeError(f"任务完成但未返回视频 URL：{resp.text}")
            return video_url

        if status in ("failed", "cancelled"):
            raise RuntimeError(f"任务 {task_id} 失败，状态：{status}，详情：{resp.text}")

        time.sleep(interval)

    raise TimeoutError(f"等待视频生成超时（{timeout}s），task_id={task_id}")


def generate_digital_human_video(
    audio_path: Path,
    config: Optional[DigitalHumanConfig] = None,
) -> str:
    """
    完整流程：提交任务 → 轮询等待 → 返回视频 URL。

    config 为 None 时使用默认配置（从环境变量读取）。
    """
    if config is None:
        config = DigitalHumanConfig()

    task_id = submit_video_task(audio_path, config)
    video_url = poll_video_task(task_id)
    return video_url
