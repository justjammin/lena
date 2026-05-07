-- Runs once when the postgres container is first initialised (mounted into
-- /docker-entrypoint-initdb.d/).  Creates the auxiliary databases for Zep and
-- Langfuse so they do not collide with the primary lena database.

SELECT 'CREATE DATABASE zep'
    WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'zep')\gexec

SELECT 'CREATE DATABASE langfuse'
    WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'langfuse')\gexec
