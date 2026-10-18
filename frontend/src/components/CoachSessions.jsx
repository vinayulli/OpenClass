import React,{useEffect,useState} from 'react';
import {Plus,MessageSquare} from 'lucide-react';
import {api} from '../api';

export default function CoachSessions({courseId,sessionId,onSelect,disabled,revision}){
  const [items,setItems]=useState([]),[busy,setBusy]=useState(false),[error,setError]=useState('');
  const path='/courses/'+encodeURIComponent(courseId)+'/coach-sessions';
  useEffect(()=>{let active=true;setError('');api(path).then(result=>{if(active)setItems(result)}).catch(e=>{if(active)setError(e.message)});return()=>{active=false}},[path,revision]);
  async function create(){setBusy(true);setError('');try{const item=await api(path,'POST');setItems(v=>[item,...v]);onSelect(item.id)}catch(e){setError(e.message)}finally{setBusy(false)}}
  return <div className="coach-sessions"><div className="section-toolbar"><div><strong>Your conversations</strong><p className="muted">Each conversation has its own history. Your learning progress stays connected.</p></div><button className="secondary" type="button" disabled={busy||disabled} onClick={create}><Plus size={17}/>New session</button></div><div className="coach-session-list" aria-label="Learning Coach conversations"><button disabled={disabled} aria-pressed={!sessionId} onClick={()=>onSelect(null)}><MessageSquare size={14}/>Previous conversations</button>{items.map(item=><button key={item.id} disabled={disabled} aria-pressed={sessionId===item.id} onClick={()=>onSelect(item.id)} title={item.title}><MessageSquare size={14}/>{item.title}</button>)}</div>{error&&<p role="alert">{error}</p>}</div>;
}
