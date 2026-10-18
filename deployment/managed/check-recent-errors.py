"""Read recent cloud failures without printing credentials or request payloads."""
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import google.auth
from google.auth.transport.requests import AuthorizedSession


def main():
    credentials, _ = google.auth.default(
        scopes=['https://www.googleapis.com/auth/cloud-platform'],
        quota_project_id='hackathon-506016',
    )
    since = (datetime.now(timezone.utc)-timedelta(minutes=30)).isoformat()
    query = f'timestamp>="{since}" AND (severity>=WARNING OR textPayload:"agent_failed" OR textPayload:"coordinator_" OR textPayload:"Traceback" OR jsonPayload.authzPolicyInfo.result="DENIED")'
    if '--gateway' in sys.argv:
        query = f'timestamp>="{since}" AND resource.type="networkservices.googleapis.com/Gateway"'
    if '--denials' in sys.argv:
        query = f'timestamp>="{since}" AND (httpRequest.status=403 OR protoPayload.serviceName="iap.googleapis.com" OR jsonPayload.statusDetails:"denied")'
    with AuthorizedSession(credentials) as session:
        response = session.post('https://logging.googleapis.com/v2/entries:list', json={
            'resourceNames': ['projects/hackathon-506016'], 'filter': query,
            'orderBy': 'timestamp desc', 'pageSize': 100,
        }, timeout=60)
        response.raise_for_status()
    entries = response.json().get('entries', [])
    target = Path('deployment/generated/recent-gateway.json' if '--gateway' in sys.argv else 'deployment/generated/recent-errors.json')
    target.write_text(json.dumps(entries, indent=2), encoding='utf-8')
    for entry in entries:
        payload = entry.get('jsonPayload', {})
        message = entry.get('textPayload') or payload.get('message') or ''
        message = re.sub(r'(?i)(bearer\s+|key=|access_token=)[^\s&]+', r'\1[redacted]', str(message))
        labels = entry.get('resource', {}).get('labels', {})
        print(json.dumps({'time': entry.get('timestamp'), 'resource': entry.get('resource', {}).get('type'),
            'service': labels.get('service_name') or labels.get('reasoning_engine_id'),
            'severity': entry.get('severity'), 'message': message[:1600],
            'status': entry.get('httpRequest', {}).get('status'),
            'gateway': payload.get('authzPolicyInfo'), 'host': payload.get('tlsSniHostname')}, ensure_ascii=True))
        if '--gateway' in sys.argv:
            print(json.dumps({'security': payload.get('enforcedGatewaySecurityPolicy'), 'http': entry.get('httpRequest')}, ensure_ascii=True))
        if '--denials' in sys.argv:
            audit = entry.get('protoPayload', {})
            print(json.dumps({'http': entry.get('httpRequest'), 'labels': entry.get('labels'), 'audit_status': audit.get('status'), 'audit_authz': audit.get('authorizationInfo'), 'details': payload.get('statusDetails')}, ensure_ascii=True))
    print('Entries:', len(entries), '; detailed log saved locally in ignored generated directory')


if __name__ == '__main__':
    main()
