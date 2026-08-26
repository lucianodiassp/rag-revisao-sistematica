BEGIN;

CREATE TABLE IF NOT EXISTS schema_migrations (
    migration_name VARCHAR(255) PRIMARY KEY,
    checksum_sha256 CHAR(64) NOT NULL,
    applied_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_verified_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (length(checksum_sha256) = 64)
);

CREATE TABLE IF NOT EXISTS service_heartbeats (
    service_name VARCHAR(50) NOT NULL,
    instance_id VARCHAR(200) NOT NULL,
    app_version VARCHAR(50) NOT NULL,
    deployment_profile VARCHAR(30) NOT NULL,
    metadata_jsonb JSONB NOT NULL DEFAULT '{}'::jsonb,
    started_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_seen_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (service_name, instance_id),
    CHECK (service_name IN ('app', 'worker')),
    CHECK (deployment_profile IN ('local', 'web_private'))
);

CREATE INDEX IF NOT EXISTS idx_service_heartbeats_latest
    ON service_heartbeats(service_name, last_seen_at DESC);

COMMIT;
