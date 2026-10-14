# שיחה קולית — GPT-Live עם client delegation

תאריך: 2026-10-14 · ענף: `feat/voice-agent` · מקור: https://developers.openai.com/api/docs/guides/voice-agents

## מטרה

לאפשר ללקוח לתאר את הארון בדיבור, בלי לשבור את העיקרון המחייב: המחיר מחושב רק בקוד, והמפרט
מתעדכן רק דרך הסוכן הקיים עם בקרת גרסאות.

## החלטה

מתוך שלוש הארכיטקטורות במדריך נבחר **GPT-Live + client delegation**:

| אפשרות | למה לא / למה כן |
|---|---|
| Realtime API (מודל אחד) | מודל הקול היה מחליט על המפרט בעצמו — עוקף את הסוכן ואת האימות. |
| GPT-Live + Responses delegation | משכפל את הסוכן הקיים במקום אחר. |
| Chained `VoicePipeline` | דורש הזרמת אודיו דרך Flask/Gunicorn הסינכרוני. |
| **GPT-Live + client delegation** | הקול רק מדבר; כל עבודה חוזרת ל-`chat_turn` הקיים. |

## זרימה

```
דפדפן ──SDP offer──▶ POST /api/inquiries/<id>/voice/session ──▶ POST /v1/live/sessions (מפתח בשרת)
     ◀──SDP answer──                                           ◀── 201 {session.id, transport.sdp}
דפדפן ⇄ OpenAI (WebRTC: אודיו + data channel "oai-events")
session.input_transcript.delta  → נאסף ב-buffer לפי start_ms
session.delegation.created      → הטקסט שעד offset_ms → POST /chat הקיים (base_version)
                                → session.commentary.append {delegation_id, content}
session.close → session.closed  → שחרור מיקרופון
```

אין WebSocket בשרת שלנו: השרת רק יוצר session. ה-sideband (`/v1/live/sessions/{id}/attach`)
נשאר אפשרות עתידית אם יידרש פיקוח צד-שרת.

## רכיבים

| קובץ | אחריות |
|---|---|
| `backend/app/services/ai/voice_session.py` | `LiveSessionClient` — בניית ה-session (הוראות בעברית, `delegation: client`) וקריאת HTTP ל-OpenAI. שגיאות → `VoiceUnavailable`. |
| `backend/app/routes/public_voice.py` | `POST /api/inquiries/<id>/voice/session`: CSRF, בעלות על הפנייה, סטטוס `collecting_details`, ולידציית SDP, הגבלת קצב. |
| `frontend/public/js/voice-transcript.js` | לוגיקה טהורה: buffer תמלול, קיצור תשובה, הודעות חלופיות. נבדק ב-`npm test`. |
| `frontend/public/js/voice.js` | WebRTC לפי ה-quickstart, תור האצלות סדרתי, סגירה מסודרת. |
| `frontend/public/js/chat.js` | `chatTurn()` משותף לכתב ולקול; ניסיון חוזר יחיד ב-409. |

## בטיחות ועלות

* מפתח ה-API לא יוצא מהשרת. הדפדפן מקבל רק SDP answer.
* הוראות הקול אוסרות ציון מחיר, הנחה או התחייבות, ואוסרות איסוף פרטים אישיים בקול.
* שמירה בזמן אמת: הדפדפן מאזין ל-`session.output_transcript.delta`; אם הקול אומר מספר ליד מטבע
  (₪/שקל/ש״ח) נשלח מיד `session.instructions.append` שמחייב תיקון.
* הקול פעיל רק כשהסוכן האמיתי פעיל (`use_real_ai` + `VOICE_ENABLED`); אחרת 503 והכפתור מוסתר.
* הגבלת קצב בשלוש שכבות: 5 שיחות ל-10 דקות לפנייה, 10 ל-10 דקות לכתובת IP (פניות חדשות לא עוקפות),
  ותקציב יומי לכל השירות (`VOICE_SESSIONS_PER_DAY`, ברירת מחדל 200). ההגבלה בזיכרון לכל worker
  (2 workers → בפועל עד פי 2); מעבר ל-Redis/DB אם יידרש.
* כשלים קבועים בהאצלה (429/422/503) מסיימים את השיחה בהודעה, במקום לולאת ״חזור שוב״.
* החיבור מוגבל בזמן: אם `session.started` לא מגיע תוך 15 שניות — ניתוק ושחרור מיקרופון.
* עלות: ‎$0.05 לדקת קול + קריאות הסוכן הקיימות.

## סיכונים פתוחים

* תמיכה בעברית אינה מתועדת בדף המודל — נדרש מבחן דיבור אמיתי (מידות, ערים, שמות חומרים).
* הקול מנסח מחדש את תשובת הסוכן; ייתכנו סטיות קטנות בניסוח.
* `gpt-live-1` אינו זמין ב-Free tier של OpenAI (החשבון הנוכחי נבדק — יש גישה).
* אין בתיעוד מגבלת משך ל-session; העלות נשלטת דרך הגבלות הקצב והסגירה ביוזמת הלקוח.
* קונפליקט גרסה שמתגלה בשמירה (אחרי ריצת הסוכן) משאיר את הודעת הלקוח בהיסטוריה — התנהגות קיימת
  גם בצ׳אט הכתוב.

## בדיקות

* `backend/tests/test_voice.py` — 19 בדיקות (הרשאות, CSRF, ולידציה, סטטוס, קצב לפנייה/IP/יומי, גוף הבקשה ל-OpenAI, שגיאות).
* `frontend/test/voice-transcript.test.js` — 8 בדיקות (buffer, קיצור, זיהוי מחיר, פיצול, סיווג כשלים).
* בדיקה ידנית מקומית: יצירת session מול OpenAI אמיתי (201), `session.started`, סגירה מסודרת.
