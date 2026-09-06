BEGIN;

ALTER TABLE background_jobs
    ADD COLUMN IF NOT EXISTS requested_by_user_id UUID;

UPDATE background_jobs AS job
SET requested_by_user_id = membership.user_id
FROM project_memberships AS membership
WHERE membership.project_id = job.project_id
  AND membership.role = 'owner'
  AND membership.is_active = TRUE
  AND job.requested_by_user_id IS NULL;

ALTER TABLE background_jobs
    DROP CONSTRAINT IF EXISTS background_jobs_requested_by_user_id_fkey;
ALTER TABLE background_jobs
    ADD CONSTRAINT background_jobs_requested_by_user_id_fkey
    FOREIGN KEY (requested_by_user_id) REFERENCES application_users(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_background_jobs_requester
    ON background_jobs(requested_by_user_id, created_at DESC)
    WHERE requested_by_user_id IS NOT NULL;

COMMENT ON COLUMN background_jobs.requested_by_user_id IS
    'Identidade que autorizou a tarefa; o worker revalida sua associação antes da execução.';

COMMIT;
