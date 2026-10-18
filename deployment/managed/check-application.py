"""Exercise the deployed application with synthetic accounts without logging credentials.

Read-only checks run by default. --chat persists two real model conversations.
Use --private for developer ADC ingress while the Cloud Run service is private.
"""
import argparse
import json
import time
import requests


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', required=True)
    parser.add_argument('--private', action='store_true')
    parser.add_argument('--chat', action='store_true')
    parser.add_argument('--assessment', action='store_true', help='Queue a teacher-requested assessment and verify the completion webhook and notification')
    args = parser.parse_args()
    headers = {}
    if args.private:
        import google.auth
        from google.auth.transport.requests import Request
        credentials, _ = google.auth.default(scopes=['https://www.googleapis.com/auth/cloud-platform'], quota_project_id='hackathon-506016')
        credentials.refresh(Request())
        if not getattr(credentials, 'id_token', None):
            raise RuntimeError('Developer ADC did not supply an ingress ID token')
        headers['X-Serverless-Authorization'] = 'Bearer '+credentials.id_token
    base = args.url.rstrip('/')
    checks = []
    student_id = None
    def call(session, method, path, payload=None):
        started = time.monotonic()
        response = session.request(method, base+path, json=payload, timeout=180)
        checks.append({'method': method, 'path': path, 'status': response.status_code, 'seconds': round(time.monotonic()-started, 2)})
        print(json.dumps(checks[-1]), flush=True)
        if not response.ok:
            # Do not print upstream error text, credentials, cookies or learner context.
            raise RuntimeError('Cloud acceptance request failed with HTTP '+str(response.status_code))
        return response.json()
    try:
        for role in ['student', 'teacher']:
            with requests.Session() as session:
                session.headers.update(headers)
                call(session, 'POST', '/api/auth/login', {'email': role+'@openclass.demo', 'password': 'OpenClass123!'})
                workspace = call(session, 'GET', '/api/workspace')
                course_id = workspace.get('course_id')
                if not course_id or not workspace.get('courses'):
                    raise RuntimeError('Demo classroom is missing')
                if role == 'student':
                    student_id = workspace['user']['id']
                call(session, 'GET', '/api/notifications')
                if args.chat:
                    message = 'Explain overfitting with a simple example from this course. Mention one practical check I can use.' if role == 'student' else 'Which taught concepts need the most support in this class? Use recorded evidence and suggest one teaching action.'
                    result = call(session, 'POST', '/api/courses/'+course_id+'/chat', {'message': message})
                    if not isinstance(result.get('message'), str) or len(result['message'].strip()) < 40:
                        raise RuntimeError('Agent did not return a substantive response')
                    print(json.dumps({'role': role, 'response_characters': len(result['message']), 'memory_status': result.get('memory_status'), 'workflow_branch': result.get('workflow_branch'), 'actions': len(result.get('actions', []))}), flush=True)
                    history = call(session, 'GET', '/api/courses/'+course_id+'/chat')
                    if not any(row.get('question') == message and row.get('response') == result['message'] for row in history):
                        raise RuntimeError('Conversation was not persisted')
                if args.assessment and role == 'teacher':
                    result = call(session, 'POST', '/api/courses/'+course_id+'/chat', {
                        'message': 'Generate a practice test for the selected learner', 'student_id': student_id,
                    })
                    jobs = [action['job_id'] for action in result.get('actions', []) if action.get('type') == 'assessment_job']
                    if len(jobs) != 1:
                        raise RuntimeError('Advisor did not dispatch exactly one specialist task')
                    deadline = time.monotonic()+240
                    while time.monotonic() < deadline:
                        job = call(session, 'GET', '/api/jobs/'+jobs[0])
                        if job['status'] in {'completed', 'failed'}:
                            break
                        time.sleep(5)
                    if job['status'] != 'completed' or not job.get('callback_received') or not job.get('exam_id'):
                        raise RuntimeError('Assessment did not complete through its authenticated webhook')
                    overview = call(session, 'GET', '/api/courses/'+course_id+'/overview')
                    exam = next((item for item in overview['exams'] if item['id'] == job['exam_id']), None)
                    if not exam or not exam.get('questions') or exam['status'] != 'draft':
                        raise RuntimeError('Generated assessment draft was not persisted')
                    notices = call(session, 'GET', '/api/notifications')
                    if not any(item.get('target_id') == exam['id'] and item.get('event') == 'assessment.ready' for item in notices['items']):
                        raise RuntimeError('Assessment completion notification is missing')
                    print(json.dumps({'assessment': 'completed', 'questions': len(exam['questions']), 'callback_received': True, 'review_required': True}), flush=True)
                call(session, 'POST', '/api/auth/logout')
        print('PASS: deployed application acceptance checks completed', flush=True)
    except Exception:
        print('FAIL: acceptance incomplete; inspect restricted cloud logs for the failing request', flush=True)
        raise


if __name__ == '__main__':
    main()
