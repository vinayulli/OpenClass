import fs from 'node:fs';
import assert from 'node:assert/strict';
const root=new URL('../mock_data/',import.meta.url);
const read=name=>JSON.parse(fs.readFileSync(new URL(name,root),'utf8'));
const manifest=read('manifest.json');
const accounts=read('accounts.json'),courses=read('courses.json'),evidence=read('evidence.json'),exams=read('exams.json'),plans=read('interventions.json');
const users=new Map(accounts.map(u=>[u.id,u])),classes=new Map(courses.map(c=>[c.id,c]));
const attempts=read('attempts.json'),assignments=read('coding_assignments.json'),reports=read('code_reviews.json');
const records=[...accounts,...courses,...evidence,...exams,...plans,...attempts,...assignments,...reports];
assert.equal(new Set(records.map(r=>r.id)).size,records.length,'Unique record IDs');
for(const r of records)assert(r.synthetic&&r.id.startsWith('mock-'),'Synthetic namespaces');
assert.equal(accounts.filter(a=>a.role==='student').length,manifest.counts.students);
assert.equal(evidence.length,manifest.counts.evidence);
for(const c of courses){
 assert.equal(users.get(c.teacher_id)?.role,'teacher');
 assert.equal(new Set(c.students).size,c.students.length);
 for(const s of c.students)assert(users.get(s)?.role==='student'&&users.get(s).org===c.org);
 const ids=new Set(c.concepts.map(x=>x.id));
 function visit(id,path=new Set()){
  assert(!path.has(id),'Concept graph is acyclic');
  assert(ids.has(id),'Known concept');
  for(const parent of c.concepts.find(x=>x.id===id).prerequisites)visit(parent,new Set([...path,id]));
 }
 for(const id of ids)visit(id);
}
for(const e of evidence){
 const c=classes.get(e.course_id);assert(c&&c.students.includes(e.student_id));
 assert(c.concepts.some(x=>x.id===e.concept_id));assert(e.score>=0&&e.score<=1&&e.confidence>0&&e.confidence<=1);
}
for(const exam of exams){
 const c=classes.get(exam.course_id),b=exam.blueprint,qs=exam.questions;
 assert(['draft','published'].includes(exam.status));assert.equal(qs.length,b.question_count);
 assert.equal(qs.reduce((s,q)=>s+q.marks,0),b.total_marks);
 assert.deepEqual([...new Set(qs.map(q=>q.concept_id))].sort(),[...b.concept_ids].sort());
 assert.equal(new Set(qs.map(q=>q.id)).size,qs.length);
 for(const q of qs){assert(c.objectives.includes(q.objective));assert(c.materials.some(m=>m.id===q.material_id));assert(q.options.includes(q.answer));assert(b.question_types.includes(q.type));}
}
for(const p of plans)assert(classes.get(p.course_id).students.includes(p.student_id)&&p.status==='draft');
for(const a of attempts){assert(exams.some(e=>e.id===a.exam_id));assert(classes.get(a.course_id).students.includes(a.student_id));assert.equal(a.score,a.results.reduce((sum,r)=>sum+r.score,0));}
for(const r of reports){assert(assignments.some(a=>a.id===r.assignment_id));assert(r.report.provisional_rating>=0&&r.report.provisional_rating<=100);}
for(const name of fs.readdirSync(new URL('agent_cases/',root))){const c=read('agent_cases/'+name);assert(c.context&&c.example_output&&c.review_criteria.length>0);}
const snapshots=read('learning_twins.json');
assert.equal(snapshots.find(t=>t.student_id==='mock-student-02').mastery,null);
const sparse=snapshots.find(t=>t.student_id==='mock-student-05').concepts.find(c=>c.id==='functions');
assert.equal(sparse.mastery,100);assert.equal(sparse.status,'insufficient evidence');
read('memory_examples.json');read('security_cases.json');
console.log(`Validated ${records.length} synthetic records, class references, concept graphs, exam constraints, 5 agent cases and insufficient-evidence examples. Python schema/Twin checks remain separate.`);
