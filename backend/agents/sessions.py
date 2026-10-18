"""Durable ADK sessions: one server-derived identity per actor/course/specialist."""
import hashlib
import json
import os
from functools import lru_cache


def session_key(org_id, course_id, actor_id, kind, conversation_id=None):
    identity = [org_id, course_id, actor_id, kind]
    if conversation_id:
        identity.append(conversation_id)
    return hashlib.sha256(json.dumps(identity, separators=(",", ":")).encode()).hexdigest()


@lru_cache(maxsize=1)
def session_service():
    from google.adk.sessions import DatabaseSessionService
    from sqlalchemy.engine import URL, make_url
    explicit = os.getenv("ADK_SESSION_DATABASE_URL") or os.getenv("DATABASE_URL")
    if explicit:
        url = make_url(explicit).set(drivername="postgresql+asyncpg")
    else:
        host = os.getenv("DB_HOST") or "/cloudsql/"+os.environ["CLOUD_SQL_CONNECTION_NAME"]
        url = URL.create("postgresql+asyncpg", username=os.getenv("DB_USER", "openclass"), password=os.getenv("DB_PASSWORD", ""), host=host if not host.startswith("/") else None, port=int(os.getenv("DB_PORT", "5433")), database=os.getenv("DB_NAME", "openclass"), query={"host": host} if host.startswith("/") else {})
    # ADK also uses a table named sessions. Keep its tables out of public,
    # which already contains the application's authentication sessions table.
    import psycopg
    with psycopg.connect(url.set(drivername="postgresql").render_as_string(hide_password=False), connect_timeout=5) as connection:
        connection.execute("SELECT pg_advisory_xact_lock(7812407)")
        connection.execute("CREATE SCHEMA IF NOT EXISTS openclass_adk")
    return DatabaseSessionService(db_url=url.render_as_string(hide_password=False), connect_args={"server_settings": {"search_path": "openclass_adk"}, "timeout": 10, "command_timeout": 20}, pool_size=3, max_overflow=2, pool_timeout=10)
