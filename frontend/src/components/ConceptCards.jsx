import React,{useState} from 'react';
import {BrainCircuit} from 'lucide-react';
import {pct} from '../utils';
import {Badge} from './common';

export default function ConceptCards({twin}){
  const [expanded,setExpanded]=useState(false);
  const concepts=twin?.concepts||[],names=new Map(concepts.map(c=>[c.id,c.name]));
  const ordered=[...concepts].sort((a,b)=>{const priority=c=>c.status==='requires review'?0:c.status==='insufficient evidence'?1:c.status==='not yet taught'?3:2;return priority(a)-priority(b)});
  const visible=expanded?ordered:ordered.slice(0,6);
  return <>{concepts.length>6&&<div className="section-toolbar"><p className="muted">{expanded?'All syllabus topics':'Priority topics'} - {visible.length} of {concepts.length}</p><button className="text-button" onClick={()=>setExpanded(value=>!value)}>{expanded?'Show priority topics':'Show full syllabus'}</button></div>}<div className="concept-cards">{visible.map(c=><article key={c.id}><div className="concept-card-top"><span className="soft-icon"><BrainCircuit size={18}/></span><strong>{pct(c.mastery)}</strong></div><h3>{c.name}</h3><Badge tone={c.status==='requires review'?'amber':['insufficient evidence','not yet taught'].includes(c.status)?'neutral':'green'}>{c.status}</Badge><div className="track"><div className="bar" style={{width:`${c.mastery||0}%`}}/></div><p>{c.evidence_count} observations - {Math.round(c.confidence*100)}% evidence confidence</p><details><summary>Evidence and prerequisites</summary><small>{c.prerequisites.length?'Builds on: '+c.prerequisites.map(id=>names.get(id)||id).join(', '):'Foundational topic'}</small>{c.evidence.map(e=><div className="evidence-item" key={e.id}>{e.source}: {Math.round(e.score*100)}%<small>{e.synthetic?'Synthetic demo - ':''}{new Date(e.at).toLocaleDateString()}</small></div>)}</details></article>)}</div></>;
}
