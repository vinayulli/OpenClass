import React from 'react';

export default function ChatAction({action}){
  if(action.type==='private_practice')return <div className="chat-action"><p>Assessment Generator: private test {action.status}. Open it to follow generation and complete the questions.</p><a className="secondary" href={`/courses/${encodeURIComponent(action.course_id||'')}/self-study?study=${encodeURIComponent(action.study_id)}`}>Open private test</a></div>;
  return <div className="chat-action">Assessment Generator {action.type==='assessment_batch'?`${action.student_count}-learner batch`:'job'}: {action.job_id||action.batch_id} · {action.status}. A draft will appear after validation.</div>;
}
