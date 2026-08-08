ALTER TABLE movies
ADD COLUMN IF NOT EXISTS now_playing_rank SMALLINT
CHECK (now_playing_rank IS NULL OR now_playing_rank > 0);

CREATE INDEX IF NOT EXISTS idx_movies_now_playing_rank
ON movies (now_playing_rank)
WHERE now_playing_rank IS NOT NULL;
