-- Run once as the database owner, then grant this role to a dedicated LOGIN
-- user created through your secret/IAM process. Do not reuse the app writer.
CREATE ROLE openclass_mcp_reader NOLOGIN;
GRANT USAGE ON SCHEMA public TO openclass_mcp_reader;
GRANT SELECT ON TABLE public.records TO openclass_mcp_reader;
-- No INSERT/UPDATE/DELETE, no sessions table, no schema CREATE privilege.
