import test from 'node:test';
import assert from 'node:assert/strict';
import {readRoute} from './navigation.js';
import {api} from './api.js';

test('deep links restore the selected classroom and page',()=>{
  assert.deepEqual(readRoute('/courses/python-foundations/tutor'),{courseId:'python-foundations',page:'tutor'});
  assert.deepEqual(readRoute('/courses/course%20one/analytics'),{courseId:'course one',page:'analytics'});
  assert.deepEqual(readRoute('/courses/%ZZ/tutor'),{courseId:'',page:'overview'});
  assert.equal(readRoute('/courses/a/unknown').page,'overview');
});

test('API timeout stops a stalled request with a retryable message',async()=>{
  const previous=globalThis.fetch;
  globalThis.fetch=async(url,{signal})=>new Promise((resolve,reject)=>signal.addEventListener('abort',()=>reject(new DOMException('Aborted','AbortError')),{once:true}));
  try{await assert.rejects(api('/courses','GET',undefined,{timeoutMs:10}),/timed out/)}finally{globalThis.fetch=previous}
});

test('API preserves actionable backend errors',async()=>{
  const previous=globalThis.fetch;
  globalThis.fetch=async()=>({ok:false,status:504,json:async()=>({detail:'Advisor timed out. Retry.'})});
  try{await assert.rejects(api('/courses/a/chat','POST',{message:'Jamie'}),error=>error.status===504&&error.message==='Advisor timed out. Retry.')}finally{globalThis.fetch=previous}
});
