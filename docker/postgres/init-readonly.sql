-- Read-only role for reporting/analytics tools (dashboards, eval exports). The API's review
-- queue uses the owner role; anything that only reads must use ledgerline_reader.
CREATE ROLE ledgerline_reader LOGIN PASSWORD 'reader-dev-only';
GRANT CONNECT ON DATABASE ledgerline TO ledgerline_reader;
GRANT USAGE ON SCHEMA public TO ledgerline_reader;
ALTER DEFAULT PRIVILEGES FOR ROLE ledgerline IN SCHEMA public GRANT SELECT ON TABLES TO ledgerline_reader;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO ledgerline_reader;
