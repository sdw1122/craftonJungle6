BEGIN;

ALTER TABLE users
    ADD COLUMN IF NOT EXISTS avatar_key VARCHAR(20);

DO $migration$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'users_avatar_key_check'
          AND conrelid = 'users'::regclass
    ) THEN
        ALTER TABLE users
            ADD CONSTRAINT users_avatar_key_check
            CHECK (
                avatar_key IS NULL
                OR avatar_key IN ('image1', 'image2', 'image3', 'image4', 'image5', 'image6', 'image7')
            );
    END IF;
END;
$migration$;

COMMIT;
