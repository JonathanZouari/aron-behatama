/**
 * לוגיקה טהורה לשיחה הקולית (ללא DOM), כדי שאפשר יהיה לבדוק אותה ב-node --test.
 *
 * GPT-Live שולח את דברי הלקוח כ-session.input_transcript.delta עם start_ms, ובנפרד
 * session.delegation.created עם offset_ms — בלי טקסט הבקשה. לכן אוספים קטעים ולוקחים
 * את כל מה שנאמר לפני נקודת ההאצלה.
 */

/** תקרת אורך לתשובה שמוחזרת לקול. המגבלה בצד OpenAI היא 500 טוקנים, ועברית צורכת יותר טוקנים לתו. */
export const MAX_COMMENTARY_CHARS = 900;

/** אורך הודעה מרבי ל-/chat (זהה למגבלת השרת). */
export const MAX_CHAT_CHARS = 2000;

export function createTranscriptBuffer() {
  let parts = [];
  return {
    add(event) {
      if (typeof event?.delta !== 'string' || !event.delta) return;
      parts = [...parts, { text: event.delta, start: Number(event.start_ms) || 0 }];
    },
    /** מחזיר ומסיר את הטקסט שנאמר לפני offsetMs (כולל), לפי סדר הזמן. */
    takeUntil(offsetMs) {
      const limit = Number(offsetMs);
      const cutoff = Number.isFinite(limit) ? limit : Infinity;
      const taken = parts.filter((p) => p.start <= cutoff).sort((a, b) => a.start - b.start);
      parts = parts.filter((p) => p.start > cutoff);
      return taken.map((p) => p.text).join('').replace(/\s+/g, ' ').trim();
    },
    get size() { return parts.length; },
  };
}

/** מקצר תשובה ארוכה בגבול משפט, כדי שלא תידחה כ-commentary. */
export function clampCommentary(text, max = MAX_COMMENTARY_CHARS) {
  const clean = String(text ?? '').trim();
  if (clean.length <= max) return clean;
  const slice = clean.slice(0, max);
  const lastStop = Math.max(slice.lastIndexOf('.'), slice.lastIndexOf('?'), slice.lastIndexOf('!'));
  return (lastStop > max * 0.5 ? slice.slice(0, lastStop + 1) : slice).trim();
}

/** מספר ליד סימן מטבע — סימן שהקול אמר מחיר, בניגוד לכלל המחייב. */
const PRICE_PATTERN = /(\d[\d,.]*\s*(₪|שקל|ש["״']?ח|ש״ח|nis|ils))|((₪|שקל|ש״ח)\s*\d)/i;

export function mentionsPrice(text) {
  return PRICE_PATTERN.test(String(text ?? ''));
}

/** מפצל דיבור ארוך לחלקים בגבול רווח, במקום לחתוך את הסוף (שם לרוב נמצאים המספרים). */
export function splitForChat(text, max = MAX_CHAT_CHARS) {
  const clean = String(text ?? '').trim();
  if (clean.length <= max) return clean ? [clean] : [];
  const parts = [];
  let rest = clean;
  while (rest.length > max) {
    const cut = rest.lastIndexOf(' ', max);
    const at = cut > 0 ? cut : max;
    parts.push(rest.slice(0, at).trim());
    rest = rest.slice(at).trim();
  }
  return rest ? [...parts, rest] : parts;
}

/**
 * כשל בהאצלה: 'stop' כשניסיון חוזר לא יעזור (הגבלת קצב, פנייה שנשלחה, שירות לא זמין) —
 * אחרת הקול יבקש מהלקוח לחזור שוב ושוב. 'retry' לתקלות רגעיות.
 */
export function delegationFailure(error) {
  return [422, 429, 503].includes(error?.status) ? 'stop' : 'retry';
}

/** הודעות קבועות שה-backend מחזיר לקול כשאין תוכן או כשיש תקלה. */
export const VOICE_FALLBACKS = {
  empty: 'לא נקלטו פרטים חדשים. שאל את הלקוח בקצרה מה הוא רוצה לתכנן בארון.',
  conflict: 'המפרט עודכן בטופס בזמן הדיבור. בקש מהלקוח לחזור על הפרט האחרון.',
  failed: 'הייתה תקלה ברישום הפרטים. בקש מהלקוח לחזור על מה שאמר, או להמשיך למלא בטופס.',
  stopped: 'אי אפשר להמשיך את השיחה הקולית כרגע. אמור ללקוח בקצרה שאפשר להמשיך בכתב ובטופס, ונפרד בנימוס.',
  noPrices: 'עצור: אסור לציין מחיר או הערכת מחיר. תקן מיד ואמור שהנגר יבדוק את המפרט וישלח הצעת מחיר מסודרת.',
};
