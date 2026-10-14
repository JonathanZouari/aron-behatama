/**
 * שיחה קולית עם GPT-Live (WebRTC, client delegation) — לפי ה-quickstart של OpenAI.
 *
 * הזרימה:
 *  1. מיקרופון + data channel ״oai-events״ → SDP offer.
 *  2. ה-offer נשלח לשרת שלנו (/voice/session), שיוצר את ה-session עם המפתח ומחזיר SDP answer.
 *  3. session.delegation.created → הטקסט שהלקוח אמר עובר ל-onDelegation (ה-/chat הקיים),
 *     והתשובה חוזרת לקול ב-session.commentary.append.
 *  4. סיום: session.close ← ממתינים ל-session.closed לפני שחרור המיקרופון.
 */
import { post } from './api.js';
import {
  createTranscriptBuffer, clampCommentary, delegationFailure, mentionsPrice, VOICE_FALLBACKS,
} from './voice-transcript.js';

const ICE_TIMEOUT_MS = 10_000;
const START_TIMEOUT_MS = 15_000;
const CLOSE_TIMEOUT_MS = 15_000;
/** זמן המתנה לקטעי תמלול שמגיעים אחרי אירוע ההאצלה. */
const TRANSCRIPT_SETTLE_MS = 600;
/** זמן לקול לומר את הודעת הסיום לפני ניתוק יזום. */
const FAREWELL_MS = 6_000;

export function voiceSupported() {
  return typeof window.RTCPeerConnection === 'function' && !!navigator.mediaDevices?.getUserMedia;
}

/**
 * @param {object} opts
 * @param {string} opts.inquiryId
 * @param {(text: string) => Promise<{reply: string, conflict?: boolean}>} opts.onDelegation
 * @param {(state: 'connecting'|'live'|'closing'|'idle'|'error', message?: string) => void} opts.onState
 */
export function createVoiceConversation({ inquiryId, onDelegation, onState }) {
  let peer = null;
  let events = null;
  let microphone = null;
  let audio = null;
  let startTimer = null;
  let closeTimer = null;
  let ready = false;
  let finalized = false;
  /** אחרי סיום/ניתוק — האצלות שבתור לא שולחות יותר ל-/chat. */
  let closed = false;
  let queue = Promise.resolve();
  let eventCounter = 0;
  let spoken = '';
  /** הודעה שתוצג אחרי סגירה מסודרת (למשל עצירה בגלל הגבלת קצב). */
  let endMessage = '';
  const transcript = createTranscriptBuffer();

  function send(event) {
    if (events?.readyState === 'open') events.send(JSON.stringify(event));
  }

  function nextEventId(prefix) {
    eventCounter += 1;
    return `${prefix}_${eventCounter}`;
  }

  function cleanup(state = 'idle', message) {
    if (closed && !peer) return;
    closed = true;
    clearTimeout(startTimer);
    clearTimeout(closeTimer);
    microphone?.getTracks().forEach((t) => t.stop());
    events?.close();
    peer?.close();
    if (audio) audio.srcObject = null;
    peer = events = microphone = null;
    ready = false;
    onState(state, message);
  }

  function reply(delegationId, content) {
    send({
      type: 'session.commentary.append',
      event_id: nextEventId('result'),
      delegation_id: delegationId,
      content: clampCommentary(content),
    });
  }

  async function handleDelegation(event) {
    const delegationId = event.delegation?.id;
    if (!delegationId || closed) return;
    await new Promise((r) => setTimeout(r, TRANSCRIPT_SETTLE_MS));
    if (closed) return;
    const text = transcript.takeUntil(event.offset_ms);
    if (!text) { reply(delegationId, VOICE_FALLBACKS.empty); return; }
    try {
      const result = await onDelegation(text);
      if (closed) return;
      reply(delegationId, result.conflict ? VOICE_FALLBACKS.conflict : (result.reply || VOICE_FALLBACKS.empty));
    } catch (err) {
      if (closed) return;
      if (delegationFailure(err) === 'stop') {
        reply(delegationId, VOICE_FALLBACKS.stopped);
        closed = true; // אין האצלות נוספות; ניתוק אחרי הודעת הפרידה
        setTimeout(() => stop(err?.message), FAREWELL_MS);
      } else {
        reply(delegationId, VOICE_FALLBACKS.failed);
      }
    }
  }

  /** שומר על הכלל המחייב גם בדיבור: אם הקול אמר מחיר — הוראה מיידית לתקן. */
  function guardPrices(delta) {
    spoken = (spoken + delta).slice(-200);
    if (!mentionsPrice(spoken)) return;
    spoken = '';
    send({ type: 'session.instructions.append', event_id: nextEventId('guard'), delegation_id: null,
      content: VOICE_FALLBACKS.noPrices });
  }

  function onEvent({ data }) {
    let event;
    try { event = JSON.parse(data); } catch { return; }
    switch (event.type) {
      case 'session.started':
        ready = true;
        clearTimeout(startTimer);
        onState('live');
        break;
      case 'session.input_transcript.delta':
        transcript.add(event);
        break;
      case 'session.output_transcript.delta':
        if (typeof event.delta === 'string') guardPrices(event.delta);
        break;
      case 'session.delegation.created':
        // האצלות מטופלות אחת-אחת כדי לשמור על סדר הגרסאות של המפרט
        queue = queue.then(() => handleDelegation(event)).catch(() => {});
        break;
      case 'session.closed':
        finalized = true;
        cleanup(endMessage ? 'error' : 'idle', endMessage || undefined);
        break;
      case 'error':
        if (!ready) cleanup('error', 'השיחה הקולית נכשלה בהתחברות');
        break;
      default:
        break;
    }
  }

  async function waitForIce(connection) {
    if (connection.iceGatheringState === 'complete') return;
    await new Promise((resolve, reject) => {
      const timeout = setTimeout(() => {
        connection.removeEventListener('icegatheringstatechange', onChange);
        reject(new Error('ice-timeout'));
      }, ICE_TIMEOUT_MS);
      function onChange() {
        if (connection.iceGatheringState !== 'complete') return;
        clearTimeout(timeout);
        connection.removeEventListener('icegatheringstatechange', onChange);
        resolve();
      }
      connection.addEventListener('icegatheringstatechange', onChange);
    });
  }

  async function start() {
    finalized = false;
    closed = false;
    onState('connecting');
    // אם החיבור לא נפתח (NAT/חומת אש) — לא להיתקע ב"מתחבר" עם מיקרופון פתוח
    startTimer = setTimeout(() => { if (!ready) cleanup('error', 'השיחה הקולית לא הצליחה להתחבר. אפשר להמשיך בכתב.'); },
      START_TIMEOUT_MS);
    try {
      const connection = new RTCPeerConnection();
      peer = connection;
      audio = audio || Object.assign(new Audio(), { autoplay: true });
      connection.addEventListener('track', (e) => {
        audio.srcObject = new MediaStream([e.track]);
        audio.play().catch(() => {});
      });
      connection.addEventListener('connectionstatechange', () => {
        if (['failed', 'closed'].includes(connection.connectionState) && !finalized && peer === connection) {
          cleanup('error', 'השיחה הקולית התנתקה');
        }
      });
      microphone = await navigator.mediaDevices.getUserMedia({ audio: true });
      if (closed) { microphone.getTracks().forEach((t) => t.stop()); return; }
      for (const track of microphone.getAudioTracks()) connection.addTrack(track, microphone);

      // ערוץ האירועים חייב להיווצר לפני ה-offer
      events = connection.createDataChannel('oai-events');
      events.addEventListener('message', onEvent);
      events.addEventListener('close', (e) => {
        if (e.target === events && !finalized) cleanup('error', 'השיחה הקולית התנתקה');
      });

      await connection.setLocalDescription(await connection.createOffer());
      await waitForIce(connection);
      const sdp = connection.localDescription?.sdp;
      if (!sdp) throw new Error('missing-sdp');

      const session = await post(`/api/inquiries/${inquiryId}/voice/session`, { sdp });
      if (closed) return; // בוטל בזמן ההמתנה; ה-session ייסגר כשהחיבור לא יוקם
      await connection.setRemoteDescription({ type: 'answer', sdp: session.sdp });
      // ה-HTTP כבר הפעיל את ה-session — אין לשלוח session.start
    } catch (err) {
      if (closed) return;
      const denied = err?.name === 'NotAllowedError';
      cleanup('error', denied ? 'אין הרשאה למיקרופון. אפשר להמשיך בכתב.' : (err?.message && err.status
        ? err.message : 'לא ניתן להתחיל שיחה קולית כרגע. אפשר להמשיך בכתב.'));
    }
  }

  /** סיום יזום. לפני session.started (כולל ביטול "מתחבר") — ניתוק מיידי. */
  function stop(message) {
    if (!ready || events?.readyState !== 'open') { cleanup(message ? 'error' : 'idle', message); return; }
    closed = true;
    endMessage = message || '';
    onState('closing');
    send({ type: 'session.close' });
    closeTimer = setTimeout(() => cleanup(endMessage ? 'error' : 'idle', endMessage || undefined), CLOSE_TIMEOUT_MS);
  }

  return { start, stop, get active() { return peer !== null; } };
}
