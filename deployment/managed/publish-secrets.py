"""Publish server credentials directly to Secret Manager, outside Terraform state."""
import base64
import os
from pathlib import Path
import secrets
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def main():
    from dotenv import load_dotenv
    load_dotenv(ROOT/".env")
    import google.auth
    from google.auth.transport.requests import AuthorizedSession
    credentials, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"], quota_project_id="hackathon-506016")
    base = "https://secretmanager.googleapis.com/v1/projects/hackathon-506016/secrets/"
    with AuthorizedSession(credentials) as session:
        def latest(name):
            response = session.get(base+name+"/versions/latest:access", timeout=30)
            if response.status_code == 404:
                return None
            if not response.ok:
                raise RuntimeError(f"Secret access failed: HTTP {response.status_code} ({name})")
            return base64.b64decode(response.json()["payload"]["data"]).decode()
        def publish(name, value):
            if not value:
                raise RuntimeError("Missing required local value for "+name)
            if latest(name) == value:
                print("Unchanged "+name, flush=True)
                return
            response = session.post(base+name+":addVersion", json={"payload": {"data": base64.b64encode(value.encode()).decode()}}, timeout=30)
            if not response.ok:
                raise RuntimeError(f"Secret upload failed: HTTP {response.status_code} ({name})")
            print("Published "+name+"; value hidden", flush=True)
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.hazmat.primitives import serialization
        private = latest("openclass-scope-private-key")
        key = serialization.load_pem_private_key(private.encode(), password=None) if private else rsa.generate_private_key(public_exponent=65537, key_size=2048)
        private = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()).decode()
        public = key.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode()
        reader_password = latest("openclass-data-db-password") or secrets.token_urlsafe(32)
        for name, value in {
            "openclass-scope-private-key": private, "openclass-scope-public-key": public,
            "openclass-gemini-api-key": os.getenv("GEMINI_API_KEY"),
            "openclass-github-token": os.getenv("GITHUB_PERSONAL_ACCESS_TOKEN") or os.getenv("GITHUB_TOKEN"),
            "openclass-db-password": os.getenv("DB_PASSWORD"),
            "openclass-data-db-password": reader_password,
            "openclass-a2a-secret": latest("openclass-a2a-secret") or secrets.token_urlsafe(48),
        }.items():
            publish(name, value)
        from backend.store import db
        from psycopg import sql
        with db() as conn:
            if not conn.execute("SELECT 1 FROM pg_roles WHERE rolname='openclass_mcp'").fetchone():
                conn.execute(sql.SQL("CREATE ROLE openclass_mcp LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION PASSWORD {}").format(sql.Literal(reader_password)))
            else:
                conn.execute(sql.SQL("ALTER ROLE openclass_mcp PASSWORD {}").format(sql.Literal(reader_password)))
            conn.execute("GRANT CONNECT ON DATABASE openclass TO openclass_mcp")
            conn.execute("GRANT USAGE ON SCHEMA public TO openclass_mcp")
            conn.execute("GRANT SELECT ON TABLE public.records TO openclass_mcp")
        print("Dedicated PostgreSQL reader configured; no application records changed", flush=True)


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print("Secret/reader provisioning failed: "+type(error).__name__+"; credentials not printed", file=sys.stderr)
        raise SystemExit(1)
