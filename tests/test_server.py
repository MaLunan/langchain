from fastapi.testclient import TestClient

from server import app
from workflow_state import WorkflowState, WorkflowStep


def test_workflow_status_returns_avatar_image_url():
    class StubStore:
        def __call__(self, session_id: str):
            assert session_id == "session-1"
            return WorkflowState(
                session_id="session-1",
                current_step=WorkflowStep.AUDIO_DONE,
                source="manual text",
                source_type="text",
                extracted_text="原文",
                final_text="确认文本",
                audio_path="/tmp/session-1.mp3",
                avatar_image_path="/tmp/session-1_avatar.png",
                video_mode="avatar",
            )

    app.state.workflow_store = StubStore()
    client = TestClient(app)

    response = client.get("/workflow/session-1/status")

    assert response.status_code == 200
    payload = response.json()
    assert payload["avatar_image_ready"] is True
    assert payload["avatar_image_url"] == "/uploads/session-1_avatar.png"
    assert payload["video_status"] == ""
    assert payload["video_error"] is None
