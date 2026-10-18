from contextlib import contextmanager


def test_pool_reused_until_configuration_changes(monkeypatch):
    from backend import store
    created = []
    class FakePool:
        def __init__(self, *args, **kwargs):
            self.closed = False
            self.options = kwargs
            created.append(self)
        def close(self):
            self.closed = True
    monkeypatch.setattr(store, "_pool", None)
    monkeypatch.setattr(store, "_pool_key", None)
    monkeypatch.setattr(store, "ConnectionPool", FakePool)
    monkeypatch.setenv("DATABASE_URL", "postgresql://localhost/pool_unit_test")
    monkeypatch.setenv("DB_POOL_MIN", "2")
    monkeypatch.setenv("DB_POOL_MAX", "6")
    first = store.connection_pool()
    assert store.connection_pool() is first
    assert len(created) == 1
    assert first.options["max_size"] == 6
    monkeypatch.setenv("DATABASE_URL", "postgresql://localhost/another_pool_unit_test")
    assert store.connection_pool() is not first
    assert first.closed
    store.close_database()
    assert created[-1].closed


def test_transaction_failure_is_forwarded_to_pool_and_connection_returned(monkeypatch):
    from backend import store
    events = []
    connection = object()
    class FakePool:
        @contextmanager
        def connection(self):
            try:
                yield connection
                events.append("commit")
            except ValueError:
                events.append("rollback")
                raise
            finally:
                events.append("returned")
    monkeypatch.setattr(store, "connection_pool", lambda: FakePool())
    with store.db() as conn:
        assert conn is connection
    try:
        with store.db():
            raise ValueError("failed write")
    except ValueError:
        pass
    assert events == ["commit", "returned", "rollback", "returned"]


def test_workspace_never_bootstraps_an_unauthorized_course(monkeypatch):
    from backend.routes import courses
    actor = {"id": "teacher", "org": "org", "role": "teacher", "password": "private"}
    records = [{"id": "allowed", "name": "Class", "code": "C", "teacher_id": "teacher", "org": "org", "students": []}, {"id": "forbidden", "name": "Private", "code": "P", "teacher_id": "other", "org": "other", "students": []}]
    monkeypatch.setattr(courses, "all_of", lambda *args: records)
    selected = []
    def overview(conn, course_id, current):
        selected.append(course_id)
        return {"course": {"id": course_id}}
    monkeypatch.setattr(courses, "classroom_overview", overview)
    result = courses.workspace("forbidden", (actor, object()))
    assert result["course_id"] == "allowed"
    assert selected == ["allowed"]
    assert "password" not in result["user"]
    monkeypatch.setattr(courses, "all_of", lambda *args: [])
    result = courses.workspace(None, (actor, object()))
    assert result["courses"] == [] and result["overview"] is None
