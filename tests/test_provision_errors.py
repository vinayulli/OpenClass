from deployment.gcp_errors import describe_error


class Response:
    status_code = 403

    def json(self):
        return {"error": {"status": "PERMISSION_DENIED", "message": "Rejected secret-password and encoded-secret", "details": [{"reason": "SERVICE_DISABLED", "metadata": {"service": "sqladmin.googleapis.com", "consumer": "projects/123"}}]}}


def test_error_diagnostics_redact_secrets():
    error = describe_error(Response(), "https://example.test/users?secret=query", {"password": "secret-password", "payload": {"data": "encoded-secret"}})
    assert "SERVICE_DISABLED" in error
    assert "sqladmin.googleapis.com" in error
    assert "secret-password" not in error
    assert "encoded-secret" not in error
    assert "secret=query" not in error


def test_non_json_error():
    class Invalid(Response):
        def json(self):
            raise ValueError("not JSON")
    assert "HTTP 403" in describe_error(Invalid(), "https://example.test")
