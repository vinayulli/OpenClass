"""Provision one Cloud SQL PostgreSQL instance; defaults to printing a plan.

uv run --extra cloud python deployment/provision-postgres.py --apply --write-env
Uses ADC. No credentials or passwords are printed or placed in command-line arguments.
"""
import argparse
import base64
import json
from pathlib import Path
import secrets
import time


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", default="hackathon-506016")
    parser.add_argument("--region", default="us-central1")
    parser.add_argument("--instance", default="openclass-postgres")
    parser.add_argument("--tier", default="db-g1-small")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--write-env", action="store_true")
    parser.add_argument("--skip-enable-apis", action="store_true", help="Skip activation if required APIs are already enabled")
    args = parser.parse_args()
    import re
    if not re.fullmatch(r"[a-z][a-z0-9-]{4,61}[a-z0-9]", args.project) or not re.fullmatch(r"[a-z][a-z0-9-]{1,95}", args.instance) or not re.fullmatch(r"[a-z]+-[a-z]+\d", args.region):
        raise ValueError("Invalid project, region or instance identifier")
    connection = f"{args.project}:{args.region}:{args.instance}"
    print(f"Target {connection}: PostgreSQL 17, Enterprise, {args.tier}, zonal, 10GB SSD with automatic growth; backups enabled; no authorized public networks.")
    if not args.apply:
        print("No cloud changes. Pass --apply to create resources using authenticated ADC.")
        return
    import google.auth
    from google.auth.transport.requests import AuthorizedSession
    credentials, _ = google.auth.default(
        scopes=["https://www.googleapis.com/auth/cloud-platform"],
        quota_project_id=args.project,
    )
    print(f"API quota project: {args.project}")
    session = AuthorizedSession(credentials)
    def call(method, url, payload=None, allow_missing=False):
        response = session.request(method, url, json=payload, timeout=60)
        if allow_missing and response.status_code == 404:
            return None
        if not response.ok:
            from gcp_errors import describe_error
            raise RuntimeError(describe_error(response, url, payload))
        return response.json() if response.content else {}
    def wait(url, sql=False):
        deadline = time.monotonic()+1800
        while time.monotonic() < deadline:
            result = call("GET", url)
            if result.get("error"):
                raise RuntimeError("GCP operation failed; inspect the operation in Cloud Console")
            complete = result.get("status") == "DONE" if sql else result.get("done")
            if complete:
                return result
            time.sleep(5)
        raise TimeoutError("GCP operation is still running. Check Cloud Console before retrying.")
    usage = "https://serviceusage.googleapis.com/v1"
    # Service Usage accepts project IDs; no Resource Manager lookup is needed.
    if not args.skip_enable_apis:
        operation = call("POST", f"{usage}/projects/{args.project}/services:batchEnable", {"serviceIds": ["sqladmin.googleapis.com", "secretmanager.googleapis.com"]})
        if operation.get("name"):
            wait(f"{usage}/{operation['name']}")
    sql = f"https://sqladmin.googleapis.com/sql/v1beta4/projects/{args.project}"
    instance = call("GET", f"{sql}/instances/{args.instance}", allow_missing=True)
    if not instance:
        result = call("POST", f"{sql}/instances", {"name": args.instance, "region": args.region, "databaseVersion": "POSTGRES_17", "settings": {"edition": "ENTERPRISE", "tier": args.tier, "availabilityType": "ZONAL", "dataDiskType": "PD_SSD", "dataDiskSizeGb": "10", "storageAutoResize": True, "ipConfiguration": {"ipv4Enabled": True, "authorizedNetworks": [], "sslMode": "ENCRYPTED_ONLY"}, "backupConfiguration": {"enabled": True, "startTime": "03:00", "pointInTimeRecoveryEnabled": True}}})
        print("Cloud SQL creation requested. Waiting for the operation…")
        wait(f"{sql}/operations/{result['name']}", sql=True)
        instance = call("GET", f"{sql}/instances/{args.instance}")
    if instance.get("region") != args.region or not instance.get("databaseVersion", "").startswith("POSTGRES_"):
        raise RuntimeError("Existing instance differs from the requested PostgreSQL/region; refusing to modify it")
    if instance.get("state") != "RUNNABLE":
        raise RuntimeError("Existing instance is not runnable; inspect its operation before retrying")
    databases = call("GET", f"{sql}/instances/{args.instance}/databases").get("items", [])
    if not any(d["name"] == "openclass" for d in databases):
        op = call("POST", f"{sql}/instances/{args.instance}/databases", {"name": "openclass"})
        wait(f"{sql}/operations/{op['name']}", sql=True)
    sm = f"https://secretmanager.googleapis.com/v1/projects/{args.project}"
    secret_id = "openclass-db-password"
    secret = call("GET", f"{sm}/secrets/{secret_id}", allow_missing=True)
    users = call("GET", f"{sql}/instances/{args.instance}/users").get("items", [])
    existing_user = any(u["name"] == "openclass" for u in users)
    latest = call("GET", f"{sm}/secrets/{secret_id}/versions/latest:access", allow_missing=True) if secret else None
    if existing_user and not latest:
        raise RuntimeError("Database user exists without a recorded secret. Refusing automatic password rotation.")
    password = base64.b64decode(latest["payload"]["data"]).decode() if latest else secrets.token_urlsafe(36)
    if not existing_user:
        op = call("POST", f"{sql}/instances/{args.instance}/users", {"name": "openclass", "password": password, "type": "BUILT_IN"})
        wait(f"{sql}/operations/{op['name']}", sql=True)
    if not secret:
        call("POST", f"{sm}/secrets?secretId={secret_id}", {"replication": {"automatic": {}}})
    if not latest:
        call("POST", f"{sm}/secrets/{secret_id}:addVersion", {"payload": {"data": base64.b64encode(password.encode()).decode()}})
    root = Path(__file__).resolve().parents[1]
    state = {"project": args.project, "region": args.region, "instance": args.instance, "connection_name": instance["connectionName"], "database": "openclass", "user": "openclass", "password_secret": f"projects/{args.project}/secrets/{secret_id}", "status": "provisioned; application connection not yet verified"}
    (root / "deployment" / "postgres.local.json").write_text(json.dumps(state, indent=2), encoding="utf-8")
    if args.write_env:
        env_path = root / ".env"
        content = env_path.read_text(encoding="utf-8") if env_path.exists() else (root / ".env.example").read_text(encoding="utf-8")
        values = {"DATABASE_URL": "", "DB_HOST": "127.0.0.1", "DB_PORT": "5433", "DB_NAME": "openclass", "DB_USER": "openclass", "DB_PASSWORD": password, "CLOUD_SQL_CONNECTION_NAME": instance["connectionName"]}
        for key, value in values.items():
            line = f"{key}={value}"
            content = re.sub(rf"(?m)^{key}=.*$", lambda _: line, content) if re.search(rf"(?m)^{key}=", content) else content+"\n"+line+"\n"
        env_path.write_text(content, encoding="utf-8")
        print("Updated ignored local .env with proxy connection settings; password not printed.")
    print("Cloud SQL provisioned:", instance["connectionName"])
    print("Start Auth Proxy, then run the application. App database access has not been verified by this provisioning script.")
    session.close()


if __name__ == "__main__":
    main()
