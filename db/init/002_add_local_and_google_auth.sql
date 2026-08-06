BEGIN;

CREATE TABLE IF NOT EXISTS auth_accounts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    provider VARCHAR(20) NOT NULL
        CHECK (provider IN ('LOCAL', 'GOOGLE')),
    login_id CITEXT,
    google_sub VARCHAR(255),
    password_hash TEXT,
    password_changed_at TIMESTAMPTZ,
    last_login_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (user_id, provider),
    CHECK (
        (
            provider = 'LOCAL'
            AND login_id IS NOT NULL
            AND password_hash IS NOT NULL
            AND google_sub IS NULL
        )
        OR
        (
            provider = 'GOOGLE'
            AND google_sub IS NOT NULL
            AND login_id IS NULL
            AND password_hash IS NULL
        )
    )
);

DO $migration$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'users'
          AND column_name = 'google_sub'
    ) THEN
        EXECUTE $sql$
            INSERT INTO auth_accounts (
                user_id,
                provider,
                google_sub,
                last_login_at,
                created_at,
                updated_at
            )
            SELECT
                id,
                'GOOGLE',
                google_sub,
                last_login_at,
                created_at,
                updated_at
            FROM users
            WHERE google_sub IS NOT NULL
            ON CONFLICT DO NOTHING
        $sql$;

        EXECUTE 'ALTER TABLE users DROP COLUMN google_sub';
    END IF;
END;
$migration$;

ALTER TABLE users ALTER COLUMN email DROP NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS uq_auth_local_login_id
    ON auth_accounts (login_id)
    WHERE provider = 'LOCAL';

CREATE UNIQUE INDEX IF NOT EXISTS uq_auth_google_sub
    ON auth_accounts (google_sub)
    WHERE provider = 'GOOGLE';

CREATE INDEX IF NOT EXISTS idx_auth_accounts_user
    ON auth_accounts (user_id);

CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_auth_accounts_updated_at ON auth_accounts;
CREATE TRIGGER trg_auth_accounts_updated_at
BEFORE UPDATE ON auth_accounts
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

COMMIT;
