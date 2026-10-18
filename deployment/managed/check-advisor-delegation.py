"""Verify a topic-specific Advisor handoff using synthetic demo data."""
import json
import time
import requests


def main():
    base = 'https://openclass-jdi6nfaqza-uc.a.run.app'
    with requests.Session() as session:
        def call(method, path, payload=None):
            started = time.monotonic()
            response = session.request(method, base+path, json=payload, timeout=180)
            print(json.dumps({'method': method, 'path': path, 'status': response.status_code, 'seconds': round(time.monotonic()-started, 2)}), flush=True)
            response.raise_for_status()
            return response.json()
        call('POST', '/api/auth/login', {'email': 'teacher@openclass.demo', 'password': 'OpenClass123!'})
        try:
            result = call('POST', '/api/courses/machine-learning/chat', {'message': 'Lets generate a test for Aarav Patel on Regularization?'})
            actions = result.get('actions', [])
            print(json.dumps({'response_characters': len(result.get('message', '')), 'action_types': [item.get('type') for item in actions]}), flush=True)
            jobs = [item['job_id'] for item in actions if item.get('type') == 'assessment_job']
            if not jobs:
                print('No job dispatched; inspect saved teacher conversation for a clarification request.', flush=True)
                return
            deadline = time.monotonic()+240
            while time.monotonic() < deadline:
                job = call('GET', '/api/jobs/'+jobs[0])
                if job['status'] in {'completed', 'failed'}:
                    break
                time.sleep(5)
            print(json.dumps({'job_id': jobs[0], 'status': job['status'], 'callback_received': job.get('callback_received'), 'exam_id': job.get('exam_id')}), flush=True)
            assert job['status'] == 'completed' and job.get('callback_received')
            overview = call('GET', '/api/courses/machine-learning/overview')
            exam = next(row for row in overview['exams'] if row['id'] == job['exam_id'])
            assert exam.get('student_id') == 'student-2', 'Expected Aarav recipient'
            concepts = {row['id']: row['name'] for row in overview['course']['concepts']}
            assert all('regularization' in concepts[identifier].lower() for identifier in exam['concept_ids'])
            print('PASS: Aarav Regularization draft persisted through specialist and webhook; teacher review required', flush=True)
        finally:
            call('POST', '/api/auth/logout')


if __name__ == '__main__':
    main()
