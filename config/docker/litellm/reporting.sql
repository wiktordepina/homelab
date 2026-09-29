-- Read-only reporting surface over LiteLLM's spend data, for consumers such as
-- Home Assistant. Re-applied on every start of the stack, so each statement is
-- idempotent.
--
-- The reporting role gets EXECUTE on these functions and no table privileges.
-- The spend and key tables carry token hashes, and LiteLLM accepts a hash in
-- place of the key it was derived from, so a plain SELECT grant would hand out
-- every virtual key.
--
-- Function bodies are strings, so Postgres records no dependency on the tables
-- they read and a LiteLLM migration that reshapes a table is never blocked by
-- this file. The cost is that the function fails at call time instead, until it
-- is updated here.

SELECT 'CREATE ROLE reporting'
WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'reporting') \gexec
ALTER ROLE reporting WITH LOGIN PASSWORD :'reporting_pwd';

CREATE SCHEMA IF NOT EXISTS reporting;
REVOKE ALL ON SCHEMA reporting FROM PUBLIC;
GRANT USAGE ON SCHEMA reporting TO reporting;

-- One row per request since the given instant. LiteLLM writes startTime as
-- naive UTC.
CREATE OR REPLACE FUNCTION reporting.spend_since(since timestamptz)
RETURNS TABLE (started_at timestamptz, key_alias text, model text, spend double precision)
LANGUAGE sql STABLE SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
  SELECT "startTime" AT TIME ZONE 'UTC',
         coalesce(nullif(metadata ->> 'user_api_key_alias', ''), 'unnamed'),
         model,
         spend
  FROM "LiteLLM_SpendLogs"
  WHERE "startTime" >= since AT TIME ZONE 'UTC'
$$;

-- Budget state of each named key. budget_spend is the spend in the current
-- budget period, not the lifetime spend.
CREATE OR REPLACE FUNCTION reporting.key_budgets()
RETURNS TABLE (key_alias text, max_budget double precision, budget_spend double precision,
               budget_duration text, budget_reset_at timestamptz)
LANGUAGE sql STABLE SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
  SELECT key_alias, max_budget, spend, budget_duration, budget_reset_at AT TIME ZONE 'UTC'
  FROM "LiteLLM_VerificationToken"
  WHERE key_alias IS NOT NULL
$$;

REVOKE ALL ON FUNCTION reporting.spend_since(timestamptz) FROM PUBLIC;
REVOKE ALL ON FUNCTION reporting.key_budgets() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION reporting.spend_since(timestamptz) TO reporting;
GRANT EXECUTE ON FUNCTION reporting.key_budgets() TO reporting;
