import React,{useEffect,useRef,useState} from 'react';
import {api} from '../api';

export default function BatchProgress({id,onComplete,onView}){
  const [batch,setBatch]=useState(null),[error,setError]=useState(''),[epoch,setEpoch]=useState(0);
  const completed=useRef(false),callback=useRef(onComplete);callback.current=onComplete;
  useEffect(()=>{let active=true,timer;completed.current=false;
    async function poll(){try{const result=await api('/assessment-batches/'+encodeURIComponent(id));if(!active)return;setBatch(result);setError('');if(['completed','finished_with_errors'].includes(result.status)){if(!completed.current){completed.current=true;callback.current?.()}return}}catch(e){if(active)setError(e.message)}if(active)timer=setTimeout(poll,4000)}
    poll();return()=>{active=false;clearTimeout(timer)};
  },[id,epoch]);
  return <section className="panel batch-progress" aria-live="polite"><div className="panel-head"><div><h3>Assessment Generator batch</h3><p>{batch?`${batch.completed} / ${batch.total} drafts completed; ${batch.failed} need attention. ${batch.status}.`:'Loading durable task progress...'}</p></div><button className="secondary" onClick={onView}>Review drafts</button></div>{error&&<p className="error">{error}</p>}<p className="muted">One A2A task per learner. Bounded parallel execution; completion arrives through authenticated webhooks.</p>{batch&&<div className="batch-tasks">{batch.jobs.map(job=><div key={job.id}><span>{job.student_id}</span><strong>{job.status.replaceAll('_',' ')}</strong>{job.error&&<small>{job.error}</small>}{job.status==='callback_failed'&&<button className="text-button" onClick={async()=>{try{await api('/jobs/'+job.id+'/retry-webhook','POST');setError('');setEpoch(value=>value+1)}catch(e){setError(e.message)}}}>Retry webhook</button>}</div>)}</div>}</section>;
}
