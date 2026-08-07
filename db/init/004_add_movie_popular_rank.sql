BEGIN;

ALTER TABLE movies
    ADD COLUMN IF NOT EXISTS popular_rank SMALLINT
    CHECK (popular_rank IS NULL OR popular_rank > 0);

CREATE INDEX IF NOT EXISTS idx_movies_popular_rank
    ON movies (popular_rank)
    WHERE popular_rank IS NOT NULL;

COMMIT;
