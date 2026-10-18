import test from 'node:test';
import assert from 'node:assert/strict';
import {messageTime,conversationMessages} from './messageTime.js';

test('formats real message times with a full date and timezone tooltip',()=>{
  const value=messageTime('2026-10-18T09:35:00+05:30','en-US');
  assert.equal(value.iso,'2026-10-18T04:05:00.000Z');
  assert.match(value.label,/\d{1,2}:\d{2}/);
  assert.match(value.full,/2026/);
  assert.equal(messageTime(null),null);
  assert.equal(messageTime('invalid'),null);
});

test('restores distinct sent/reply times without inventing legacy question times',()=>{
  const rows=conversationMessages([{question:'Q',response:'A',question_at:'2026-10-18T04:00:00Z',response_at:'2026-10-18T04:00:10Z',duration_ms:10000},{question:'Old',response:'Old reply',at:'2026-10-17T04:00:00Z'}]);
  assert.equal(rows[0].at,'2026-10-18T04:00:00Z');
  assert.equal(rows[1].at,'2026-10-18T04:00:10Z');
  assert.equal(rows[1].duration_ms,10000);
  assert.equal(rows[2].at,undefined);
  assert.equal(rows[3].at,'2026-10-17T04:00:00Z');
});
