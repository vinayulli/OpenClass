"""Live feature acceptance using synthetic demo accounts. Persists generated demo work."""
import argparse
import json
import time
import requests


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('feature', choices=['path', 'coding', 'intervention', 'practice', 'web', 'complete-assessment', 'batch'])
    parser.add_argument('--url', default='https://openclass-jdi6nfaqza-uc.a.run.app')
    parser.add_argument('--public', action='store_true')
    parser.add_argument('--job-id')
    args = parser.parse_args()
    headers = {}
    if not args.public:
        import google.auth
        from google.auth.transport.requests import Request
        credentials, _ = google.auth.default(scopes=['https://www.googleapis.com/auth/cloud-platform'], quota_project_id='hackathon-506016')
        credentials.refresh(Request())
        headers['X-Serverless-Authorization'] = 'Bearer '+credentials.id_token
    student, teacher = requests.Session(), requests.Session()
    for session in [student, teacher]:
        session.headers.update(headers)

    def call(session, method, path, payload=None, expected=None):
        started = time.monotonic()
        response = session.request(method, args.url.rstrip('/')+path, json=payload, timeout=180)
        print(json.dumps({'method': method, 'path': path, 'status': response.status_code, 'seconds': round(time.monotonic()-started, 2)}), flush=True)
        if expected is not None:
            assert response.status_code == expected
            return None
        if not response.ok:
            raise RuntimeError('Acceptance HTTP '+str(response.status_code)+'; inspect restricted cloud logs')
        return response.json()

    def poll(load, select, seconds=240):
        deadline = time.monotonic()+seconds
        while time.monotonic() < deadline:
            item = select(load())
            if item and item.get('status') in {'completed', 'failed', 'finished_with_errors'}:
                assert item['status'] == 'completed', 'Generation failed; inspect restricted cloud logs'
                return item
            time.sleep(5)
        raise TimeoutError('Feature did not complete within its acceptance window')

    try:
        for role, session in [('student', student), ('teacher', teacher)]:
            call(session, 'POST', '/api/auth/login', {'email': role+'@openclass.demo', 'password': 'OpenClass123!'})
        workspace = call(student, 'GET', '/api/workspace')
        cid, sid = workspace['course_id'], workspace['user']['id']
        prefix = '/api/courses/'+cid
        overview = call(teacher, 'GET', prefix+'/overview')
        taught = [c['id'] for c in overview['course']['concepts'] if c.get('teaching_status') != 'planned']
        if args.feature == 'path':
            result = call(teacher, 'POST', prefix+'/learning-paths/regenerate', {'student_ids': [sid]})
            wanted = result['paths'][0]['id']
            row = poll(lambda: call(teacher, 'GET', prefix+'/learning-paths'),
                       lambda rows: next((r.get('latest_request') for r in rows if r['student_id'] == sid and r.get('latest_request', {}).get('id') == wanted), None))
            assert row['output']['steps'] and row['output'].get('reference_catalog')
            assert all(step['references'] and len(step['explanation']) >= 120 for step in row['output']['steps'])
            print(json.dumps({'learning_path': 'completed', 'steps': len(row['output']['steps']), 'references': len(row['output']['reference_catalog'])}), flush=True)
        elif args.feature == 'coding':
            report = call(student, 'POST', prefix+'/code-reviews', {'url': 'https://github.com/octocat/Spoon-Knife'})
            assert report['status'] == 'teacher_review_required' and report['report']['summary']
            print(json.dumps({'coding': 'completed', 'review_required': True, 'confidence': report['report']['confidence']}), flush=True)
        elif args.feature == 'intervention':
            report = call(teacher, 'POST', prefix+'/students/'+sid+'/interventions')
            assert report['status'] == 'draft' and report['lesson'] and report['concept_id'] in {c['id'] for c in overview['course']['concepts']}
            print(json.dumps({'intervention': 'completed', 'review_required': True}), flush=True)
        elif args.feature in {'practice', 'web'}:
            session = call(student, 'POST', prefix+'/coach-sessions')
            message = ('Create a private practice test with 2 multiple-choice questions on '+taught[0]+'.'
                       if args.feature == 'practice' else 'Search the public web for beginner-friendly resources explaining overfitting in machine learning. Use your web research specialist and return reference links.')
            result = call(student, 'POST', prefix+'/chat', {'conversation_id': session['id'], 'message': message})
            assert result.get('message')
            if args.feature == 'practice':
                action = next(a for a in result['actions'] if a.get('type') == 'private_practice')
                assert action['url'].startswith('/courses/'+cid+'/self-study?study=')
                row = poll(lambda: call(student, 'GET', prefix+'/self-study'), lambda rows: next((r for r in rows if r['id'] == action['study_id']), None))
                assert len(row['output']['questions']) == 2
                call(teacher, 'GET', prefix+'/self-study', expected=403)
                print(json.dumps({'private_practice': 'completed', 'questions': 2, 'teacher_access': 'denied'}), flush=True)
            else:
                assert result.get('sources'), 'Web research returned no source links'
                print(json.dumps({'web_research': 'completed', 'sources': len(result['sources'])}), flush=True)
        elif args.feature == 'complete-assessment':
            if not args.job_id:
                raise ValueError('--job-id is required for a previously generated demo assessment')
            job = call(teacher, 'GET', '/api/jobs/'+args.job_id)
            exam = next(e for e in overview['exams'] if e['id'] == job['exam_id'])
            assert exam['blueprint'].get('student_id') == sid and all(q['type'] == 'mcq' and q['answer'] in q['options'] for q in exam['questions'])
            call(teacher, 'POST', '/api/exams/'+exam['id']+'/publish')
            notices = call(student, 'GET', '/api/notifications')
            assert any(n['target_id'] == exam['id'] and n['event'] == 'assessment.published' for n in notices['items'])
            attempt = call(student, 'POST', '/api/exams/'+exam['id']+'/attempt')
            assert all('answer' not in q and 'rubric' not in q for q in attempt['exam']['questions'])
            aid = attempt['attempt']['id']
            call(student, 'PUT', '/api/attempts/'+aid+'/answers', {'answers': {q['id']: q['answer'] for q in exam['questions']}})
            result = call(student, 'POST', '/api/attempts/'+aid+'/submit')
            assert result['status'] == 'graded' and result['score'] == result['total_marks']
            print(json.dumps({'assessment_submission': 'graded', 'score': result['score'], 'total_marks': result['total_marks'], 'student_notification': 'verified', 'answer_key_hidden_before_submission': True}), flush=True)
        elif args.feature == 'batch':
            ids = overview['course']['students']
            assert len(ids) == 10
            batch = call(teacher, 'POST', prefix+'/assessment-batches', {'student_ids': ids, 'teacher_request': 'Generate a standard practice test for everyone on the same concept, with different questions per learner.', 'blueprint': {'title': 'Machine Learning concept practice', 'kind': 'practice', 'concept_ids': [taught[0]], 'question_count': 2, 'total_marks': 4, 'duration_minutes': 10, 'difficulty': 'beginner', 'question_types': ['mcq']}})
            row = poll(lambda: call(teacher, 'GET', '/api/assessment-batches/'+batch['id']), lambda r: r, seconds=600)
            assert row['completed'] == 10 and row['failed'] == 0 and all(j['callback_received'] for j in row['jobs'])
            exams = call(teacher, 'GET', prefix+'/overview')['exams']
            generated = [e for e in exams if e.get('batch_id') == batch['id']]
            assert len(generated) == 10
            prompts = [' '.join(q['prompt'].casefold().split()) for e in generated for q in e['questions']]
            assert len(prompts) == len(set(prompts))
            assert all(e['blueprint']['concept_ids'] == [taught[0]] for e in generated)
            print(json.dumps({'standard_batch': 'completed', 'learners': 10, 'distinct_question_prompts': len(prompts), 'callbacks_verified': 10}), flush=True)
        print('PASS: '+args.feature+' through deployed application', flush=True)
    finally:
        for session in [student, teacher]:
            try:
                session.post(args.url.rstrip('/')+'/api/auth/logout', timeout=15)
            finally:
                session.close()


if __name__ == '__main__':
    main()
