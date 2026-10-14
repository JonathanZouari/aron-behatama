"""יצירת שיחה קולית ב-GPT-Live (OpenAI) במצב client delegation.

הקול רק מדבר ומקשיב. כל עבודה אמיתית (חילוץ מפרט, שאלות השלמה) מואצלת חזרה לאפליקציה:
הדפדפן מקבל session.delegation.created, שולח את דברי הלקוח ל-/chat הקיים (אותו סוכן,
אותן גרסאות, אותו מנוע תמחור) ומחזיר את התשובה ב-session.commentary.append.
מפתח ה-API נשאר בשרת; הדפדפן מקבל רק את תשובת ה-SDP.
"""
from __future__ import annotations

import logging
from typing import Any, Callable

import requests

log = logging.getLogger(__name__)

LIVE_SESSIONS_URL = "https://api.openai.com/v1/live/sessions"
REQUEST_TIMEOUT_SECONDS = 20

VOICE_INSTRUCTIONS = """\
אתה הקול של ״ארון בהתאמה״ — נגרייה שמתכננת ארונות בהתאמה אישית. דבר עברית בלבד, בטון חם ומקצועי,
במשפטים קצרים. שאל שאלה אחת בכל פעם.

חלוקת עבודה:
- כל מה שהלקוח אומר על הארון (מידות, עומק, דלתות, מגירות, מדפים, חומר, חזיתות, גימור, טריקה שקטה,
  הובלה, התקנה, עיר, דרישות מיוחדות) או כל שאלה על האפשרויות — העבר מיד ל-backend (delegate).
  אל תחליט, אל תסכם ואל תמציא פרטים בעצמך.
- כשמגיעה תשובה מה-backend, אמור אותה בנאמנות ובקצרה, בלי להוסיף מידע משלך.
- בזמן שה-backend עובד אפשר לומר משהו קצר כמו ״רגע, אני רושם״.

כללים מחייבים:
- לעולם אל תציין מחיר, הערכת מחיר, הנחה, זמני ייצור או התחייבות כלשהי. אם שואלים על מחיר —
  הסבר שהנגר בודק את המפרט ושולח הצעת מחיר מסודרת.
- כשהלקוח אומר מספרים, חזור עליהם כדי לוודא שהבנת נכון.
- אל תבקש ואל תחזור על פרטים אישיים (טלפון, כתובת מלאה, תעודת זהות). את פרטי הקשר ממלאים בטופס.

בתחילת השיחה: ברך בקצרה ובקש מהלקוח לתאר את הארון שהוא רוצה.
"""


class VoiceUnavailable(Exception):
    """שירות הקול אינו זמין (אין הגדרה, שגיאת רשת או תשובה לא תקינה מ-OpenAI)."""


PostFn = Callable[..., Any]


class LiveSessionClient:
    def __init__(self, api_key: str, model: str, voice: str, post: PostFn = requests.post):
        self._api_key = api_key
        self._model = model
        self._voice = voice
        self._post = post

    def session_config(self) -> dict:
        return {
            "model": self._model,
            "instructions": VOICE_INSTRUCTIONS,
            "audio": {"output": {"voice": self._voice}},
            "delegation": {"type": "client"},
        }

    def create(self, sdp: str) -> dict:
        """שולח את ה-SDP offer של הדפדפן ומחזיר {session_id, sdp} עם ה-SDP answer."""
        body = {"session": self.session_config(), "transport": {"type": "webrtc", "sdp": sdp}}
        headers = {"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"}
        try:
            response = self._post(LIVE_SESSIONS_URL, json=body, headers=headers, timeout=REQUEST_TIMEOUT_SECONDS)
        except Exception as exc:  # noqa: BLE001 — כל כשל רשת מטופל כשירות לא זמין
            log.warning("GPT-Live session request failed: %s", type(exc).__name__)
            raise VoiceUnavailable("שירות הקול אינו זמין כרגע") from exc

        if response.status_code != 201:
            log.warning("GPT-Live session rejected: HTTP %s", response.status_code)
            raise VoiceUnavailable("שירות הקול אינו זמין כרגע")
        try:
            payload = response.json()
            return {"session_id": payload["session"]["id"], "sdp": payload["transport"]["sdp"]}
        except (ValueError, KeyError, TypeError) as exc:
            log.warning("GPT-Live session response malformed")
            raise VoiceUnavailable("שירות הקול אינו זמין כרגע") from exc
