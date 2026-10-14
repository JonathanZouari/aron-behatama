import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  createTranscriptBuffer, clampCommentary, MAX_COMMENTARY_CHARS, mentionsPrice, splitForChat, delegationFailure,
} from '../public/js/voice-transcript.js';

test('takes speech said before the delegation offset, in time order', () => {
  const buf = createTranscriptBuffer();
  buf.add({ delta: ' 260', start_ms: 1500 });
  buf.add({ delta: 'ארון 240 על', start_ms: 1000 });
  buf.add({ delta: 'עוד משהו', start_ms: 5000 });
  assert.equal(buf.takeUntil(2000), 'ארון 240 על 260');
  assert.equal(buf.size, 1);
  assert.equal(buf.takeUntil(6000), 'עוד משהו');
  assert.equal(buf.size, 0);
});

test('returns empty string when nothing was said', () => {
  const buf = createTranscriptBuffer();
  assert.equal(buf.takeUntil(1000), '');
});

test('ignores malformed events and treats missing offset as everything', () => {
  const buf = createTranscriptBuffer();
  buf.add(null);
  buf.add({ delta: '' });
  buf.add({ delta: 42 });
  buf.add({ delta: 'שלום' });
  assert.equal(buf.takeUntil(undefined), 'שלום');
});

test('clampCommentary keeps short text and cuts long text at a sentence end', () => {
  assert.equal(clampCommentary('  קצר. '), 'קצר.');
  const long = 'משפט ראשון ארוך. '.repeat(200);
  const out = clampCommentary(long);
  assert.ok(out.length <= MAX_COMMENTARY_CHARS);
  assert.ok(out.endsWith('.'));
});

test('clampCommentary hard-cuts when there is no sentence end', () => {
  const out = clampCommentary('א'.repeat(3000));
  assert.equal(out.length, MAX_COMMENTARY_CHARS);
});

test('mentionsPrice flags spoken prices and ignores measurements', () => {
  assert.equal(mentionsPrice('זה יעלה בערך 8,000 ₪'), true);
  assert.equal(mentionsPrice('המחיר הוא 5000 שקל'), true);
  assert.equal(mentionsPrice('בסביבות 3000 ש״ח'), true);
  assert.equal(mentionsPrice('ארון ברוחב 240 ס״מ ועומק 60'), false);
  assert.equal(mentionsPrice('הנגר ישלח הצעת מחיר מסודרת'), false);
});

test('splitForChat keeps short text and splits long text on whitespace', () => {
  assert.deepEqual(splitForChat('קצר'), ['קצר']);
  const long = 'מילה '.repeat(1000).trim();
  const parts = splitForChat(long, 2000);
  assert.ok(parts.length > 1);
  assert.ok(parts.every((p) => p.length <= 2000));
  assert.equal(parts.join(' '), long);
});

test('delegationFailure stops the conversation on non-transient errors', () => {
  assert.equal(delegationFailure({ status: 429 }), 'stop');
  assert.equal(delegationFailure({ status: 422 }), 'stop');
  assert.equal(delegationFailure({ status: 503 }), 'stop');
  assert.equal(delegationFailure({ status: 0 }), 'retry');
  assert.equal(delegationFailure(new Error('x')), 'retry');
});
