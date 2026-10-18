export async function consumeChatEvents(body,onProgress){
  const reader=body.getReader(),decoder=new TextDecoder();
  let buffer='';
  try{
    while(true){
      const {done,value}=await reader.read();
      if(done)throw new Error('The response stream ended before completion. Please retry.');
      buffer+=decoder.decode(value,{stream:true});
      let boundary;
      while((boundary=buffer.indexOf('\n\n'))!==-1){
        const block=buffer.slice(0,boundary);buffer=buffer.slice(boundary+2);
        const lines=block.split('\n'),event=lines.find(line=>line.startsWith('event: '))?.slice(7);
        const data=lines.filter(line=>line.startsWith('data: ')).map(line=>line.slice(6)).join('\n');
        if(!event||!data)continue;
        const payload=JSON.parse(data);
        if(event==='progress')onProgress?.(payload);
        if(event==='error'){const error=new Error(payload.message);error.status=payload.status;throw error}
        if(event==='result')return payload;
      }
    }
  }finally{await reader.cancel().catch(()=>{});reader.releaseLock()}
}

export async function streamChat(courseId,body,{signal,onProgress}={}){
  const controller=new AbortController();let timedOut=false;
  const abort=()=>controller.abort();signal?.addEventListener('abort',abort,{once:true});if(signal?.aborted)abort();
  const timer=setTimeout(()=>{timedOut=true;abort()},120000);
  try{
    const response=await fetch(`/api/courses/${encodeURIComponent(courseId)}/chat/stream`,{method:'POST',credentials:'include',headers:{'Content-Type':'application/json',Accept:'text/event-stream'},body:JSON.stringify(body),signal:controller.signal});
    if(!response.ok){let detail;try{detail=(await response.json()).detail}catch{}const error=new Error(typeof detail==='string'?detail:`Request failed (${response.status})`);error.status=response.status;throw error}
    if(!response.body)throw new Error('Streaming is unavailable. Refresh and retry.');
    return await consumeChatEvents(response.body,onProgress);
  }catch(error){if(timedOut)throw new Error('The assistant timed out. Retry your question.');throw error}
  finally{clearTimeout(timer);signal?.removeEventListener('abort',abort)}
}
