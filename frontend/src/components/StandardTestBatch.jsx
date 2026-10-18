import React,{useRef,useState} from 'react';
import {Sparkles} from 'lucide-react';
import {api} from '../api';
import {Field} from './common';

export default function StandardTestBatch({data,onGenerated}){
  const [topics,setTopics]=useState([]),[count,setCount]=useState(5),[difficulty,setDifficulty]=useState('beginner'),[busy,setBusy]=useState(false),[error,setError]=useState(''),[message,setMessage]=useState('');
  const request=useRef(null);
  async function submit(e){e.preventDefault();setBusy(true);setError('');setMessage('');try{
    const body={student_ids:data.students.map(s=>s.id),blueprint:{title:'Standard concept test - individual variant',kind:'practice',concept_ids:topics,question_count:Number(count),total_marks:Number(count)*2,duration_minutes:20,difficulty,question_types:['mcq'],release_feedback:true},teacher_request:'Create a standard test for every enrolled student using exactly the same selected concepts and settings, with distinct questions for each student.'};
    const fingerprint=JSON.stringify(body);if(request.current?.fingerprint!==fingerprint)request.current={fingerprint,key:crypto.randomUUID()};
    const result=await api(`/courses/${data.course.id}/assessment-batches`,'POST',body,{headers:{'Idempotency-Key':request.current.key}});
    request.current=null;onGenerated?.(result);setMessage(`Queued ${result.student_count} separate test variants. Review and publish each draft in Assessments.`);
  }catch(e){setError(e.message)}finally{setBusy(false)}}
  return <section className="panel studio-pad"><h2>Same concepts, different questions for everyone</h2><p>Generate one test variant per enrolled student. All variants use the same selected topics, difficulty, question count and marks. Each student sees only their assigned test after you review and publish it.</p>{error&&<p className="error" role="alert">{error}</p>}{message&&<p role="status">{message}</p>}<form onSubmit={submit}><Field label="Shared concepts"><div className="suggestions">{data.course.concepts.map(c=><label key={c.id}><input type="checkbox" checked={topics.includes(c.id)} onChange={e=>setTopics(ids=>e.target.checked?[...ids,c.id]:ids.filter(id=>id!==c.id))}/>{c.name}</label>)}</div></Field><div className="form-grid"><Field label="Questions per student"><input type="number" min={Math.max(1,topics.length)} max={20} value={count} onChange={e=>setCount(e.target.value)} required/></Field><Field label="Shared difficulty"><select value={difficulty} onChange={e=>setDifficulty(e.target.value)}><option value="beginner">Beginner</option><option value="intermediate">Intermediate</option><option value="advanced">Advanced</option></select></Field></div><p>{Number(count)*2} marks · 20 minutes · {data.students.length} students · MCQs</p><button className="primary" disabled={busy||!topics.length||!data.students.length}><Sparkles size={16}/>{busy?'Queueing variants...':`Generate ${data.students.length} different tests on these concepts`}</button></form></section>;
}
