"""שיחה קולית (GPT-Live, client delegation): יצירת session בשרת בלבד, הרשאות, ולידציה והגבלת קצב."""
import pytest

from app.services.ai.voice_session import LiveSessionClient, VoiceUnavailable

from .conftest import csrf

SDP = "v=0\r\no=- 1 2 IN IP4 127.0.0.1\r\ns=-\r\n"


class FakeLive:
    """מחליף את הקריאה ל-OpenAI: מתעד את ה-SDP ומחזיר תשובה קבועה."""

    def __init__(self, fail=False):
        self.calls = []
        self.fail = fail

    def create(self, sdp: str) -> dict:
        self.calls.append(sdp)
        if self.fail:
            raise VoiceUnavailable("שירות הקול אינו זמין כרגע")
        return {"session_id": "live_test", "sdp": "v=0\r\nanswer\r\n"}


@pytest.fixture
def voice(container):
    fake = FakeLive()
    container.voice = fake
    return fake


def _inquiry(client):
    headers = csrf(client)
    inquiry = client.post("/api/inquiries", headers=headers).get_json()["data"]
    return inquiry, headers


def test_creates_session_and_returns_answer_sdp(client, voice):
    inquiry, headers = _inquiry(client)
    r = client.post(f"/api/inquiries/{inquiry['id']}/voice/session", json={"sdp": SDP}, headers=headers)
    assert r.status_code == 201, r.get_json()
    data = r.get_json()["data"]
    assert data == {"session_id": "live_test", "sdp": "v=0\r\nanswer\r\n"}
    assert voice.calls == [SDP]


def test_voice_unavailable_without_real_ai(client, container):
    container.voice = None
    inquiry, headers = _inquiry(client)
    r = client.post(f"/api/inquiries/{inquiry['id']}/voice/session", json={"sdp": SDP}, headers=headers)
    assert r.status_code == 503
    assert r.get_json()["voice_unavailable"] is True


def test_openai_failure_maps_to_503(client, container):
    container.voice = FakeLive(fail=True)
    inquiry, headers = _inquiry(client)
    r = client.post(f"/api/inquiries/{inquiry['id']}/voice/session", json={"sdp": SDP}, headers=headers)
    assert r.status_code == 503
    assert r.get_json()["voice_unavailable"] is True


def test_requires_access_to_inquiry(app, voice):
    owner = app.test_client()
    inquiry, _ = _inquiry(owner)
    stranger = app.test_client()
    r = stranger.post(f"/api/inquiries/{inquiry['id']}/voice/session", json={"sdp": SDP}, headers=csrf(stranger))
    assert r.status_code == 404
    assert voice.calls == []


def test_requires_csrf(client, voice):
    inquiry, _ = _inquiry(client)
    r = client.post(f"/api/inquiries/{inquiry['id']}/voice/session", json={"sdp": SDP})
    assert r.status_code == 403
    assert voice.calls == []


@pytest.mark.parametrize("body", [{}, {"sdp": ""}, {"sdp": "hello"}, {"sdp": "v=0" + "x" * 20000},
                                  {"sdp": SDP, "extra": 1}])
def test_rejects_invalid_sdp(client, voice, body):
    inquiry, headers = _inquiry(client)
    r = client.post(f"/api/inquiries/{inquiry['id']}/voice/session", json=body, headers=headers)
    assert r.status_code == 422
    assert voice.calls == []


def test_only_while_collecting_details(client, voice):
    from .conftest import create_submitted_inquiry

    inquiry = create_submitted_inquiry(client)
    r = client.post(f"/api/inquiries/{inquiry['id']}/voice/session", json={"sdp": SDP}, headers=csrf(client))
    assert r.status_code == 422
    assert voice.calls == []


def test_rate_limited_per_inquiry(client, voice, container):
    inquiry, headers = _inquiry(client)
    url = f"/api/inquiries/{inquiry['id']}/voice/session"
    codes = [client.post(url, json={"sdp": SDP}, headers=headers).status_code
             for _ in range(container.settings.voice_sessions_per_window + 1)]
    assert codes[-1] == 429
    assert all(c == 201 for c in codes[:-1])


def test_health_reports_voice_flag(client, container):
    container.voice = None
    assert client.get("/api/health").get_json()["voice"] is False
    container.voice = FakeLive()
    assert client.get("/api/health").get_json()["voice"] is True


# ---- LiveSessionClient: גוף הבקשה ל-OpenAI ----

class FakeResponse:
    def __init__(self, status, payload):
        self.status_code = status
        self._payload = payload

    def json(self):
        return self._payload


def test_client_sends_client_delegation_session():
    sent = {}

    def fake_post(url, json, headers, timeout):
        sent.update(url=url, json=json, headers=headers)
        return FakeResponse(201, {"session": {"id": "live_1"}, "transport": {"type": "webrtc", "sdp": "ans"}})

    live = LiveSessionClient(api_key="sk-test", model="gpt-live-1", voice="marin", post=fake_post)
    assert live.create(SDP) == {"session_id": "live_1", "sdp": "ans"}
    assert sent["url"] == "https://api.openai.com/v1/live/sessions"
    assert sent["headers"]["Authorization"] == "Bearer sk-test"
    session = sent["json"]["session"]
    assert session["model"] == "gpt-live-1"
    assert session["delegation"] == {"type": "client"}
    assert session["audio"]["output"]["voice"] == "marin"
    assert "עברית" in session["instructions"] and "מחיר" in session["instructions"]
    assert sent["json"]["transport"] == {"type": "webrtc", "sdp": SDP}


@pytest.mark.parametrize("status,payload", [(400, {"error": {"message": "bad"}}), (201, {"unexpected": True})])
def test_client_raises_voice_unavailable_on_bad_response(status, payload):
    live = LiveSessionClient(api_key="k", model="m", voice="v",
                             post=lambda *a, **k: FakeResponse(status, payload))
    with pytest.raises(VoiceUnavailable):
        live.create(SDP)


def test_client_wraps_network_errors():
    def boom(*a, **k):
        raise OSError("network down")

    live = LiveSessionClient(api_key="k", model="m", voice="v", post=boom)
    with pytest.raises(VoiceUnavailable):
        live.create(SDP)


def test_rate_limited_per_client_ip_across_inquiries(app, voice, container):
    client = app.test_client()
    headers = csrf(client)
    limit = container.settings.voice_sessions_per_ip
    codes = []
    for _ in range(limit + 1):
        inquiry = client.post("/api/inquiries", headers=headers).get_json()["data"]
        codes.append(client.post(f"/api/inquiries/{inquiry['id']}/voice/session", json={"sdp": SDP},
                                 headers={**headers, "X-Forwarded-For": "203.0.113.7"}).status_code)
    assert codes[-1] == 429
    assert all(c == 201 for c in codes[:-1])


def test_global_daily_budget(app, voice, container):
    from app.services.security import RateLimiter

    container.voice_daily_limiter = RateLimiter(2, 86400)
    codes = []
    for i in range(3):
        client = app.test_client()
        inquiry, headers = _inquiry(client)
        codes.append(client.post(f"/api/inquiries/{inquiry['id']}/voice/session", json={"sdp": SDP},
                                 headers={**headers, "X-Forwarded-For": f"203.0.113.{i}"}).status_code)
    assert codes == [201, 201, 429]
