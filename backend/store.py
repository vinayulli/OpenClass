"""PostgreSQL persistence. JSON payloads keep curriculum extensible."""
import hashlib
import json
import os
import secrets
import psycopg
import threading
from psycopg_pool import ConnectionPool
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")


def now():
    return datetime.now(timezone.utc).isoformat()


def uid():
    return secrets.token_hex(12)


def password_hash(password, salt=None):
    salt = salt or secrets.token_hex(16)
    return salt + ":" + hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 160000).hex()


def check_password(password, stored):
    return secrets.compare_digest(password_hash(password, stored.split(":")[0]), stored)


_pool = None
_pool_key = None
_pool_lock = threading.Lock()


def connection_settings():
    url = os.getenv("DATABASE_URL", "").strip()
    if url:
        return url, {"connect_timeout": 5}
    cloud_instance = os.getenv("CLOUD_SQL_CONNECTION_NAME", "")
    host = os.getenv("DB_HOST") or ("/cloudsql/"+cloud_instance if cloud_instance else "127.0.0.1")
    return "", dict(host=host, port=int(os.getenv("DB_PORT", "5433")), dbname=os.getenv("DB_NAME", "openclass"), user=os.getenv("DB_USER", "openclass"), password=os.getenv("DB_PASSWORD", ""), connect_timeout=5)


def connection_pool():
    """One bounded, thread-safe pool per API process/configuration."""
    global _pool, _pool_key
    conninfo, kwargs = connection_settings()
    minimum, maximum = int(os.getenv("DB_POOL_MIN", "2")), int(os.getenv("DB_POOL_MAX", "6"))
    key = (conninfo, tuple(sorted(kwargs.items())), minimum, maximum)
    with _pool_lock:
        if _pool is None or _pool_key != key:
            if _pool is not None:
                _pool.close()
            _pool = ConnectionPool(conninfo, kwargs=kwargs, min_size=minimum, max_size=maximum, timeout=10, max_waiting=40, max_idle=300, max_lifetime=1800, reconnect_timeout=15, name="openclass", open=True)
            _pool_key = key
        return _pool


def warm_database():
    connection_pool().wait(timeout=20)


def close_database():
    global _pool, _pool_key
    with _pool_lock:
        if _pool is not None:
            _pool.close()
            _pool = None
            _pool_key = None


@contextmanager
def db():
    # Pool context commits/rolls back and returns the connection for reuse.
    # Connections never cross transaction or request boundaries while checked out.
    with connection_pool().connection() as conn:
        yield conn


def put(conn, kind, data):
    conn.execute("INSERT INTO records(id,kind,data) VALUES(%s,%s,%s) ON CONFLICT(id) DO UPDATE SET data=excluded.data", (data["id"], kind, json.dumps(data)))
    return data


def get(conn, kind, id):
    row = conn.execute("SELECT data FROM records WHERE kind=%s AND id=%s", (kind, id)).fetchone()
    return json.loads(row[0]) if row else None


def all_of(conn, kind):
    return [json.loads(r[0]) for r in conn.execute("SELECT data FROM records WHERE kind=%s ORDER BY sequence", (kind,))]


def many_of(conn, kinds):
    """Fetch a classroom read snapshot in one round trip, preserving record order."""
    result = {kind: [] for kind in kinds}
    for kind, data in conn.execute("SELECT kind,data FROM records WHERE kind=ANY(%s) ORDER BY sequence", (list(kinds),)):
        result[kind].append(json.loads(data))
    return result


def audit(conn, actor, action, target):
    put(conn, "audit", {"id": uid(), "actor": actor, "action": action, "target": target, "at": now()})


def initialize():
    with db() as conn:
        conn.execute("SELECT pg_advisory_xact_lock(7812401)")
        conn.execute("CREATE TABLE IF NOT EXISTS records(sequence BIGSERIAL UNIQUE,id TEXT PRIMARY KEY,kind TEXT NOT NULL,data TEXT NOT NULL)")
        conn.execute("CREATE INDEX IF NOT EXISTS records_kind ON records(kind)")
        conn.execute("CREATE TABLE IF NOT EXISTS sessions(token TEXT PRIMARY KEY,user_id TEXT NOT NULL,expires DOUBLE PRECISION NOT NULL)")
        conn.execute("CREATE TABLE IF NOT EXISTS schema_version(version INTEGER PRIMARY KEY)")
        conn.execute("INSERT INTO schema_version VALUES(1) ON CONFLICT DO NOTHING")
        if os.getenv("OPENCLASS_DEMO", "true").lower() != "true" or all_of(conn, "user"):
            return
        put(conn, "user", {"id": "teacher-demo", "name": "Alex Morgan", "email": "teacher@openclass.demo", "role": "teacher", "org": "demo", "password": password_hash("OpenClass123!")})
        names = ["Jamie Chen", "Aarav Patel", "Maya Williams", "Sofia Garcia", "Noah Kim", "Isha Rao"]
        for i in range(10):
            put(conn, "user", {"id": f"student-{i+1}", "name": names[i] if i < len(names) else f"Demo Learner {i+1}", "email": "student@openclass.demo" if i == 0 else f"student{i+1}@openclass.demo", "role": "student", "org": "demo", "password": password_hash("OpenClass123!")})
        course = {"id": "python-foundations", "org": "demo", "teacher_id": "teacher-demo", "name": "Python & software foundations", "description": "From understanding a concept to building something with it.", "code": "CS 201", "color": "violet", "objectives": ["Write reusable Python functions", "Apply encapsulation and composition", "Build reliable programs with tests"], "concepts": [{"id": "functions", "name": "Functions", "prerequisites": []}, {"id": "parameters", "name": "Parameters & returns", "prerequisites": ["functions"]}, {"id": "encapsulation", "name": "Encapsulation", "prerequisites": ["functions"]}, {"id": "composition", "name": "Composition", "prerequisites": ["encapsulation"]}, {"id": "testing", "name": "Unit testing", "prerequisites": ["functions", "parameters"]}], "students": [f"student-{i+1}" for i in range(10)], "materials": [{"id": "intro", "title": "Functions: a practical introduction", "content": "A function groups reusable behavior. Parameters receive input; return passes a value to the caller. Composition combines objects instead of inheriting behavior. Encapsulation places data and operations behind a clear interface. Tests compare actual behavior to expected outcomes.", "created_at": now()}], "created_at": now()}
        put(conn, "course", course)
        for i in range(6):
            for j, concept in enumerate(course["concepts"]):
                for k in range(3):
                    put(conn, "evidence", {"id": uid(), "course_id": course["id"], "student_id": f"student-{i+1}", "concept_id": concept["id"], "source": "Synthetic baseline quiz", "source_id": "demo-baseline", "score": [1, .5, 0][(i+j+k) % 3] if j > 1 else [1, 1, .5][(i+k) % 3], "kind": "quiz", "confidence": 1, "at": now(), "synthetic": True})
