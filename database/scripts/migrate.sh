#!/bin/sh
set -eu

psql --set ON_ERROR_STOP=1 <<'SQL'
CREATE TABLE IF NOT EXISTS schema_migrations (
    migration_name VARCHAR(255) PRIMARY KEY,
    checksum_sha256 CHAR(64) NOT NULL,
    applied_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_verified_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (length(checksum_sha256) = 64)
);
SQL

echo '{"level":"info","event":"migration_batch_started","component":"migrate","category":"database"}'

for migration in /migrations/0*.sql; do
    migration_name=$(basename "$migration")
    migration_checksum=$(sha256sum "$migration" | awk '{print $1}')
    echo "{\"level\":\"info\",\"event\":\"migration_started\",\"component\":\"migrate\",\"category\":\"database\",\"migration\":\"${migration_name}\"}"
    psql --set ON_ERROR_STOP=1 --file "$migration"
    psql --set ON_ERROR_STOP=1 \
        --set migration_name="$migration_name" \
        --set migration_checksum="$migration_checksum" <<'SQL'
INSERT INTO schema_migrations
    (migration_name, checksum_sha256, applied_at, last_verified_at)
VALUES (
    :'migration_name', :'migration_checksum', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
)
ON CONFLICT (migration_name) DO UPDATE
SET checksum_sha256 = EXCLUDED.checksum_sha256,
    last_verified_at = CURRENT_TIMESTAMP;
SQL
    echo "{\"level\":\"info\",\"event\":\"migration_succeeded\",\"component\":\"migrate\",\"category\":\"database\",\"migration\":\"${migration_name}\"}"
done

echo '{"level":"info","event":"migration_batch_succeeded","component":"migrate","category":"database"}'
