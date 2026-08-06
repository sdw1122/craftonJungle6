BEGIN;

ALTER TABLE users
    ADD COLUMN IF NOT EXISTS gender VARCHAR(20),
    ADD COLUMN IF NOT EXISTS birth_date DATE,
    ADD COLUMN IF NOT EXISTS onboarding_completed_at TIMESTAMPTZ;

DO $migration$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'users_gender_check'
          AND conrelid = 'users'::regclass
    ) THEN
        ALTER TABLE users
            ADD CONSTRAINT users_gender_check
            CHECK (
                gender IS NULL
                OR gender IN ('MALE', 'FEMALE', 'OTHER', 'UNDISCLOSED')
            );
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'users_birth_date_check'
          AND conrelid = 'users'::regclass
    ) THEN
        ALTER TABLE users
            ADD CONSTRAINT users_birth_date_check
            CHECK (
                birth_date IS NULL
                OR birth_date >= DATE '1900-01-01'
            );
    END IF;
END;
$migration$;

CREATE TABLE IF NOT EXISTS user_favorite_genres (
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    genre_id SMALLINT NOT NULL REFERENCES genres(id) ON DELETE RESTRICT,
    priority SMALLINT NOT NULL CHECK (priority BETWEEN 1 AND 3),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id, genre_id),
    UNIQUE (user_id, priority)
);

CREATE INDEX IF NOT EXISTS idx_user_favorite_genres_genre
    ON user_favorite_genres (genre_id, user_id);

CREATE OR REPLACE FUNCTION validate_user_birth_date()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.birth_date IS NOT NULL AND NEW.birth_date > CURRENT_DATE THEN
        RAISE EXCEPTION 'birth_date cannot be in the future'
            USING ERRCODE = '22007';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_users_birth_date ON users;
CREATE TRIGGER trg_users_birth_date
BEFORE INSERT OR UPDATE OF birth_date ON users
FOR EACH ROW EXECUTE FUNCTION validate_user_birth_date();

COMMIT;
