import test from 'node:test';
import assert from 'node:assert/strict';
import {consumeChatEvents} from './chatStream.js';

function chunks(parts){return new ReadableStream({start(controller){for(const part of parts)controller.enqueue(new TextEncoder().encode(part));controller.close()}})}
test('reads split SSE progress and final response without displaying heartbeats',async()=>{
  const stages=[];
  const result=await consumeChatEvents(chunks([': keep-alive\n\nevent: pro','gress\ndata: {"stage":"records","message":"Reading"}\n','\nevent: result\ndata: {"message":"Ready"}\n\n']),item=>stages.push(item));
  assert.deepEqual(stages,[{stage:'records',message:'Reading'}]);
  assert.equal(result.message,'Ready');
});
test('surfaces streamed authorization errors and interrupted responses',async()=>{
  await assert.rejects(consumeChatEvents(chunks(['event: error\ndata: {"message":"Denied","status":403}\n\n'])),error=>error.status===403&&error.message==='Denied');
  await assert.rejects(consumeChatEvents(chunks(['event: progress\ndata: {"stage":"records"}\n\n'])),/ended before completion/);
});
