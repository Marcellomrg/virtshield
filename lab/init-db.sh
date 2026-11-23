#!/bin/sh
(
    set -eu
    export APP_SECRET="$(cat "${APP_PASSWORD_FILE:-/run/secrets/app_password}")"
    psql -X -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<'SQL'
\getenv app_password APP_SECRET
CREATE ROLE app_user LOGIN PASSWORD :'app_password';
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
GRANT USAGE ON SCHEMA public TO app_user;
CREATE TABLE public.labels (id integer PRIMARY KEY, label text NOT NULL);
INSERT INTO public.labels VALUES (1, 'alpha'), (2, 'beta'), (3, 'gamma'), (4, 'delta');
GRANT SELECT ON public.labels TO app_user;
SQL
)
