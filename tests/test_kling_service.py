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


def test_get_credentials_raises_when_missing():
    from kling_service import _get_credentials
    with patch.dict(os.environ, {}, clear=True):
        # Ensure both keys are absent
        os.environ.pop("KLING_ACCESS_KEY_ID", None)
        os.environ.pop("KLING_ACCESS_KEY_SECRET", None)
        with pytest.raises(EnvironmentError, match="KLING_ACCESS_KEY_ID"):
            _get_credentials()


# ── 轮询 ────────────────────────────────────────────────────────────────────

def test_poll_task_returns_url_on_succeed():
    from kling_service import _poll_task
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {
        "data": {"status": "succeed", "video_url": "https://example.com/v.mp4"}
    }
    with patch("kling_service.requests.get", return_value=mock_resp), \
         patch("kling_service._make_jwt", return_value="tok"), \
         patch.dict(os.environ, {"KLING_ACCESS_KEY_ID": "ak", "KLING_ACCESS_KEY_SECRET": "sk"}):
        url = _poll_task("task_abc", timeout=10)
    assert url == "https://example.com/v.mp4"


def test_poll_task_raises_on_failed():
    from kling_service import _poll_task
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {"data": {"status": "failed"}}
    with patch("kling_service.requests.get", return_value=mock_resp), \
         patch("kling_service._make_jwt", return_value="tok"), \
         patch.dict(os.environ, {"KLING_ACCESS_KEY_ID": "ak", "KLING_ACCESS_KEY_SECRET": "sk"}):
        with pytest.raises(RuntimeError, match="任务.*失败"):
            _poll_task("task_xyz", timeout=10)


# ── 数字人口播 ───────────────────────────────────────────────────────────────

def test_generate_avatar_video_calls_lip_sync(tmp_path):
    from kling_service import generate_avatar_video

    audio = tmp_path / "test.mp3"
    audio.write_bytes(b"fake_audio")

    # First post call: audio upload → returns audio_url
    upload_resp = MagicMock()
    upload_resp.raise_for_status = MagicMock()
    upload_resp.json.return_value = {"data": {"url": "https://cdn.kling.ai/audio.mp3"}}

    # Second post call: lip-sync task submission → returns task_id
    task_resp = MagicMock()
    task_resp.raise_for_status = MagicMock()
    task_resp.json.return_value = {"data": {"task_id": "avatar_task_1"}}

    poll_resp = MagicMock()
    poll_resp.raise_for_status = MagicMock()
    poll_resp.json.return_value = {
        "data": {"status": "succeed", "video_url": "https://cdn.kling.ai/avatar.mp4"}
    }

    with patch("kling_service.requests.post", side_effect=[upload_resp, task_resp]) as mock_post, \
         patch("kling_service.requests.get", return_value=poll_resp), \
         patch("kling_service._make_jwt", return_value="tok"), \
         patch.dict(os.environ, {"KLING_ACCESS_KEY_ID": "ak", "KLING_ACCESS_KEY_SECRET": "sk",
                                  "KLING_AVATAR_ID": "avatar_001"}):
        url = generate_avatar_video(audio)

    assert url == "https://cdn.kling.ai/avatar.mp4"
    # Verify the second POST called lip-sync
    assert "lip-sync" in mock_post.call_args_list[1][0][0]
