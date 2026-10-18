export async function api(path, method='GET', body, options={}) {
  const controller = new AbortController();
  let timedOut=false;
  const timeout=setTimeout(()=>{timedOut=true;controller.abort()}, options.timeoutMs ?? (path.endsWith('/chat')?120000:30000));
  const abort=()=>controller.abort();
  options.signal?.addEventListener('abort',abort,{once:true});
  if(options.signal?.aborted)controller.abort();
  try {
    const response = await fetch('/api'+path, {method, credentials:'include', signal:controller.signal, headers:{...options.headers,...(body ? {'Content-Type':'application/json'} : {})}, body:body ? JSON.stringify(body) : undefined});
    if (!response.ok) { let message; try { const data=await response.json(); message=typeof data.detail==='string' ? data.detail : data.detail?.map(x=>x.msg).join('; '); } catch {} const error=new Error(message || `Request failed (${response.status})`);error.status=response.status;throw error; }
    return await response.json();
  } catch(error) {
    if(timedOut)throw new Error('The request timed out. Check the backend connection and retry.');
    throw error;
  } finally {
    clearTimeout(timeout);
    options.signal?.removeEventListener('abort',abort);
  }
}
