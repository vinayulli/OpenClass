# One shared Cloud SQL PostgreSQL instance

Target: `hackathon-506016:us-central1:openclass-postgres`. This is the requested cloud persistence path. Provisioning has **not run** in the restricted agent session.

The initial development configuration is PostgreSQL 17 Enterprise, `db-g1-small`, zonal, 10GB SSD with automatic growth and backups. This small shared-core configuration is for the hackathon; concurrency/latency targets still require load testing. It incurs Google Cloud charges while running. The instance has a public connector endpoint but no authorized public networks. Cloud SQL Auth Proxy or a managed Cloud SQL connection supplies authenticated, encrypted access.

Run in your authenticated ordinary terminal:

```powershell
gcloud auth login
gcloud auth application-default login
gcloud auth application-default set-quota-project hackathon-506016
uv sync --extra cloud --python 3.12
uv run --extra cloud python deployment/provision-postgres.py --apply --write-env
docker compose --profile cloud up -d cloud-sql-proxy
uv run uvicorn backend.main:app --reload
```

The provisioner explicitly uses its `--project` argument for API quota as well as resource creation. If an error names a different `consumer=projects/...`, check ADC quota configuration or `GOOGLE_CLOUD_QUOTA_PROJECT`. Setting only `gcloud config set project` does not update an existing ADC quota project. The calling identity needs `serviceusage.services.use` on the quota project.

The script creates exactly one named instance if absent, an `openclass` database, an application database user, and a random password stored in Secret Manager. It writes the password to ignored `.env` only when `--write-env` is provided. It does not print credentials, replace an existing unrelated instance, or automatically rotate an existing password. If interrupted after user creation but before the secret is saved, it stops for manual reconciliation rather than changing credentials unexpectedly. Re-running after an in-flight instance creation requires checking the existing operation first.

The Auth Proxy Docker service mounts your existing ADC file read-only from `%APPDATA%/gcloud/application_default_credentials.json` and publishes **localhost:5433**. The API runs on Windows and connects to that local proxy port. Your ADC identity needs Cloud SQL connection permissions in the project. The cloud SQL API must be enabled and billing active. A terminal unable to access credentials or the Docker engine cannot start this connection.

For Cloud Run, use the same `CLOUD_SQL_CONNECTION_NAME`, attach the Cloud SQL instance to the service, set `DB_HOST=/cloudsql/hackathon-506016:us-central1:openclass-postgres`, `DB_PORT=5432`, `DB_NAME=openclass`, `DB_USER=openclass`, and load `DB_PASSWORD` from Secret Manager. Keep `DATABASE_URL` empty. Grant the **specific API/MCP workload identities** Cloud SQL connection access and access to this one password secret. Do not grant broad project Owner/Editor access.

The PostgreSQL record tables are initialized on API startup. The MCP service relies on that schema and the same database; start/initialize the API first. After connecting, verify `/api/health`, teacher/student login, assessment submission, and evidence persistence. These runtime checks have not yet run.

The old local Docker PostgreSQL service remains available only under the `local` Compose profile as an optional development fallback. Existing data is not deleted or migrated automatically. No local database was successfully started in this session, so there is no verified local data migration to perform.

References: [Cloud SQL instance creation](https://docs.cloud.google.com/sql/docs/postgres/create-instance), [Cloud SQL Auth Proxy](https://docs.cloud.google.com/sql/docs/postgres/connect-auth-proxy).
