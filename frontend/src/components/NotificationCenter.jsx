import React, {useEffect, useRef, useState} from 'react';
import {Bell, Check, X} from 'lucide-react';
import {api} from '../api';

export default function NotificationCenter({onNavigate}) {
  const [feed,setFeed]=useState({items:[],unread:0}),[open,setOpen]=useState(false),[popup,setPopup]=useState(null),[error,setError]=useState('');
  const seen=useRef(null),active=useRef(true);
  async function refresh(){
    try {
      const result=await api('/notifications');
      if(!active.current)return;
      if(seen.current){const next=result.items.find(n=>!seen.current.has(n.id)&&!n.read_at);if(next)setPopup(next)}
      seen.current=new Set([...(seen.current||[]),...result.items.map(n=>n.id)]);
      setFeed(result);setError('');
    }catch(e){if(active.current)setError(e.message)}
  }
  useEffect(()=>{active.current=true;refresh();const timer=setInterval(()=>{if(!document.hidden)refresh()},8000);const visible=()=>{if(!document.hidden)refresh()};document.addEventListener('visibilitychange',visible);return()=>{active.current=false;clearInterval(timer);document.removeEventListener('visibilitychange',visible)}},[]);
  useEffect(()=>{if(!popup)return;const timer=setTimeout(()=>setPopup(null),7000);return()=>clearTimeout(timer)},[popup?.id]);
  async function visit(item){try{await api(`/notifications/${encodeURIComponent(item.id)}/read`,'POST');await refresh();setOpen(false);setPopup(null);onNavigate(item)}catch(e){setError(e.message)}}
  return <div className="notification-center"><button className="notification-toggle" aria-label={`Notifications, ${feed.unread} unread`} aria-expanded={open} onClick={()=>setOpen(v=>!v)}><Bell size={18}/>{feed.unread>0&&<span>{feed.unread}</span>}</button>{open&&<section className="notification-panel" aria-label="Notifications"><div className="notification-heading"><strong>Notifications</strong><button className="text-button" onClick={async()=>{try{await api('/notifications/read-all','POST');await refresh()}catch(e){setError(e.message)}}}><Check size={13}/>Read all</button></div>{error&&<p className="error" role="alert">{error}</p>}{!feed.items.length&&<p className="muted">Task updates will appear here. This feed refreshes while the app is open.</p>}{feed.items.map(item=><button className={'notification-item '+(!item.read_at?'unread':'')} key={item.id} onClick={()=>visit(item)}><strong>{item.title}</strong><p>{item.message}</p><small>{new Date(item.created_at).toLocaleString()}</small></button>)}</section>}{popup&&<div className="notification-popup" role="status"><button className="icon-button" aria-label="Dismiss task update" onClick={()=>setPopup(null)}><X size={15}/></button><strong>{popup.title}</strong><p>{popup.message}</p><button className="text-button" onClick={()=>visit(popup)}>Open update</button></div>}</div>;
}
