import React, { useEffect, useState } from 'react';
import { BrainCircuit, RefreshCw } from 'lucide-react';
import { api } from '../api';
import { Badge } from './common';

export default function ManagedMemory({courseId, studentId}) {
  const [data, setData] = useState(null);
  const [error, setError] = useState('');
  const [version, setVersion] = useState(0);
  useEffect(() => {
    let active = true;
    setData(null); setError('');
    api(`/courses/${courseId}/students/${studentId}/memories`)
      .then(result => { if (active) setData(result); })
      .catch(error => { if (active) setError(error.message); });
    return () => { active = false; };
  }, [courseId, studentId, version]);
  return <section className="managed-memory">
    <div className="panel-head">
      <div><h3><BrainCircuit size={16}/> Learner memories</h3><p>Long-term learning context, scoped to this learner and course.</p></div>
      <button className="icon-button" aria-label="Refresh learner memories" onClick={() => setVersion(v => v + 1)}><RefreshCw size={16}/></button>
    </div>
    <div className="memory-content">
      {error && <p className="error" role="alert">{error}</p>}
      {!data && !error && <p className="muted">Loading managed memory status…</p>}
      {data && <>
        <Badge tone={data.provider === 'disabled' ? 'amber' : 'purple'}>{data.provider === 'disabled' ? 'GEAP Memory Bank not enabled' : data.provider}</Badge>
        {data.memories.length ? data.memories.map((fact, i) => <p key={i}>{fact}</p>) : <p className="muted">No managed memory facts are available yet. Missing memory is not evidence of a learning gap.</p>}
        <div className="memory-status">{data.sync.length} evidence summaries · {data.sync.filter(s => s.status === 'synced').length} synchronized · {data.sync.filter(s => ['pending', 'processing'].includes(s.status)).length} pending · {data.sync.filter(s => s.status === 'failed').length} failed</div>
      </>}
    </div>
  </section>;
}
