BEGIN;

CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS citext;
CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email CITEXT UNIQUE,
    nickname VARCHAR(50) NOT NULL UNIQUE,
    status VARCHAR(20) NOT NULL DEFAULT 'ACTIVE'
        CHECK (status IN ('ACTIVE', 'BLOCKED', 'WITHDRAWN')),
    gender VARCHAR(20)
        CHECK (gender IS NULL OR gender IN ('MALE', 'FEMALE', 'OTHER', 'UNDISCLOSED')),
    birth_date DATE
        CHECK (birth_date IS NULL OR birth_date >= DATE '1900-01-01'),
    onboarding_completed_at TIMESTAMPTZ,
    email_verified_at TIMESTAMPTZ,
    last_login_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    deleted_at TIMESTAMPTZ
);

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

CREATE TABLE IF NOT EXISTS user_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    refresh_token_hash VARCHAR(64) NOT NULL UNIQUE,
    expires_at TIMESTAMPTZ NOT NULL,
    revoked_at TIMESTAMPTZ,
    device_info JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (expires_at > created_at)
);

CREATE TABLE IF NOT EXISTS ott_providers (
    id SMALLSERIAL PRIMARY KEY,
    code VARCHAR(30) NOT NULL UNIQUE,
    name VARCHAR(50) NOT NULL,
    logo_url TEXT,
    is_active BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS user_ott_subscriptions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    provider_id SMALLINT NOT NULL REFERENCES ott_providers(id) ON DELETE RESTRICT,
    started_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    ended_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (ended_at IS NULL OR ended_at > started_at)
);

CREATE TABLE IF NOT EXISTS movies (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tmdb_id BIGINT UNIQUE,
    original_title VARCHAR(300) NOT NULL,
    overview TEXT,
    release_date DATE,
    runtime_minutes SMALLINT CHECK (runtime_minutes IS NULL OR runtime_minutes > 0),
    original_language VARCHAR(10),
    age_rating VARCHAR(20),
    poster_url TEXT,
    backdrop_url TEXT,
    popular_rank SMALLINT CHECK (popular_rank IS NULL OR popular_rank > 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS movie_titles (
    id BIGSERIAL PRIMARY KEY,
    movie_id UUID NOT NULL REFERENCES movies(id) ON DELETE CASCADE,
    locale VARCHAR(10) NOT NULL,
    title VARCHAR(300) NOT NULL,
    title_type VARCHAR(20) NOT NULL
        CHECK (title_type IN ('PRIMARY', 'ORIGINAL', 'ALIAS')),
    UNIQUE (movie_id, locale, title_type, title)
);

CREATE TABLE IF NOT EXISTS genres (
    id SMALLSERIAL PRIMARY KEY,
    code VARCHAR(30) NOT NULL UNIQUE,
    name VARCHAR(50) NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS movie_genres (
    movie_id UUID NOT NULL REFERENCES movies(id) ON DELETE CASCADE,
    genre_id SMALLINT NOT NULL REFERENCES genres(id) ON DELETE RESTRICT,
    PRIMARY KEY (movie_id, genre_id)
);

CREATE TABLE IF NOT EXISTS user_favorite_genres (
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    genre_id SMALLINT NOT NULL REFERENCES genres(id) ON DELETE RESTRICT,
    priority SMALLINT NOT NULL CHECK (priority BETWEEN 1 AND 3),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id, genre_id),
    UNIQUE (user_id, priority)
);

CREATE TABLE IF NOT EXISTS people (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tmdb_id BIGINT UNIQUE,
    primary_name VARCHAR(200) NOT NULL,
    birth_date DATE
);

CREATE TABLE IF NOT EXISTS person_names (
    id BIGSERIAL PRIMARY KEY,
    person_id UUID NOT NULL REFERENCES people(id) ON DELETE CASCADE,
    locale VARCHAR(10) NOT NULL,
    name VARCHAR(200) NOT NULL,
    name_type VARCHAR(20) NOT NULL
        CHECK (name_type IN ('PRIMARY', 'ALIAS')),
    UNIQUE (person_id, locale, name_type, name)
);

CREATE TABLE IF NOT EXISTS movie_credits (
    id BIGSERIAL PRIMARY KEY,
    movie_id UUID NOT NULL REFERENCES movies(id) ON DELETE CASCADE,
    person_id UUID NOT NULL REFERENCES people(id) ON DELETE CASCADE,
    credit_type VARCHAR(20) NOT NULL
        CHECK (credit_type IN ('ACTOR', 'DIRECTOR')),
    character_name VARCHAR(200),
    billing_order SMALLINT CHECK (billing_order IS NULL OR billing_order >= 0)
);

CREATE TABLE IF NOT EXISTS ott_availabilities (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    movie_id UUID NOT NULL REFERENCES movies(id) ON DELETE CASCADE,
    provider_id SMALLINT NOT NULL REFERENCES ott_providers(id) ON DELETE RESTRICT,
    region_code CHAR(2) NOT NULL DEFAULT 'KR',
    offer_type VARCHAR(20) NOT NULL
        CHECK (offer_type IN ('SUBSCRIPTION', 'FREE', 'RENT', 'BUY')),
    available_from DATE NOT NULL,
    available_until DATE,
    content_url TEXT,
    source VARCHAR(50),
    source_updated_at TIMESTAMPTZ,
    last_checked_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (available_until IS NULL OR available_until > available_from),
    UNIQUE (movie_id, provider_id, region_code, offer_type, available_from)
);

CREATE TABLE IF NOT EXISTS user_movie_library (
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    movie_id UUID NOT NULL REFERENCES movies(id) ON DELETE CASCADE,
    is_wishlisted BOOLEAN NOT NULL DEFAULT FALSE,
    watch_status VARCHAR(20)
        CHECK (watch_status IS NULL OR watch_status IN ('WATCHING', 'WATCHED')),
    started_at TIMESTAMPTZ,
    watched_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id, movie_id),
    CHECK (watch_status <> 'WATCHED' OR watched_at IS NOT NULL)
);

CREATE TABLE IF NOT EXISTS movie_reviews (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    movie_id UUID NOT NULL REFERENCES movies(id) ON DELETE CASCADE,
    rating_half_steps SMALLINT NOT NULL CHECK (rating_half_steps BETWEEN 1 AND 10),
    content TEXT,
    contains_spoiler BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    deleted_at TIMESTAMPTZ,
    UNIQUE (user_id, movie_id)
);

CREATE TABLE IF NOT EXISTS ranking_snapshots (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    provider_id SMALLINT NOT NULL REFERENCES ott_providers(id) ON DELETE RESTRICT,
    region_code CHAR(2) NOT NULL DEFAULT 'KR',
    ranking_date DATE NOT NULL,
    ranking_type VARCHAR(30) NOT NULL
        CHECK (ranking_type IN ('DAILY_POPULAR', 'WEEKLY_POPULAR')),
    source VARCHAR(50),
    collected_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (provider_id, region_code, ranking_date, ranking_type)
);

CREATE TABLE IF NOT EXISTS ranking_items (
    snapshot_id UUID NOT NULL REFERENCES ranking_snapshots(id) ON DELETE CASCADE,
    movie_id UUID NOT NULL REFERENCES movies(id) ON DELETE CASCADE,
    rank SMALLINT NOT NULL CHECK (rank > 0),
    score NUMERIC,
    PRIMARY KEY (snapshot_id, movie_id),
    UNIQUE (snapshot_id, rank)
);

CREATE TABLE IF NOT EXISTS recommendation_runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    provider_id SMALLINT REFERENCES ott_providers(id) ON DELETE SET NULL,
    recommendation_type VARCHAR(30) NOT NULL
        CHECK (recommendation_type IN ('PERSONALIZED', 'ENDING_SOON', 'UPCOMING')),
    model_name VARCHAR(100) NOT NULL,
    feature_version VARCHAR(50) NOT NULL,
    context JSONB,
    generated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMPTZ NOT NULL,
    CHECK (expires_at > generated_at)
);

CREATE TABLE IF NOT EXISTS recommendation_items (
    run_id UUID NOT NULL REFERENCES recommendation_runs(id) ON DELETE CASCADE,
    movie_id UUID NOT NULL REFERENCES movies(id) ON DELETE CASCADE,
    rank SMALLINT NOT NULL CHECK (rank > 0),
    score NUMERIC(8, 6) NOT NULL CHECK (score >= 0 AND score <= 1),
    reason_text VARCHAR(500),
    reason_codes JSONB,
    PRIMARY KEY (run_id, movie_id),
    UNIQUE (run_id, rank)
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_active_user_ott
    ON user_ott_subscriptions (user_id, provider_id)
    WHERE ended_at IS NULL;

CREATE UNIQUE INDEX IF NOT EXISTS uq_auth_local_login_id
    ON auth_accounts (login_id)
    WHERE provider = 'LOCAL';

CREATE UNIQUE INDEX IF NOT EXISTS uq_auth_google_sub
    ON auth_accounts (google_sub)
    WHERE provider = 'GOOGLE';

CREATE INDEX IF NOT EXISTS idx_auth_accounts_user
    ON auth_accounts (user_id);

CREATE INDEX IF NOT EXISTS idx_user_sessions_active
    ON user_sessions (user_id, expires_at)
    WHERE revoked_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_movie_titles_search
    ON movie_titles USING GIN (title gin_trgm_ops);

CREATE INDEX IF NOT EXISTS idx_person_names_search
    ON person_names USING GIN (name gin_trgm_ops);

CREATE INDEX IF NOT EXISTS idx_movie_credits_person_type
    ON movie_credits (person_id, credit_type, movie_id);

CREATE INDEX IF NOT EXISTS idx_movie_credits_movie_type
    ON movie_credits (movie_id, credit_type, billing_order);

CREATE INDEX IF NOT EXISTS idx_movie_genres_genre
    ON movie_genres (genre_id, movie_id);

CREATE INDEX IF NOT EXISTS idx_movies_popular_rank
    ON movies (popular_rank)
    WHERE popular_rank IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_user_favorite_genres_genre
    ON user_favorite_genres (genre_id, user_id);

CREATE INDEX IF NOT EXISTS idx_availability_provider_period
    ON ott_availabilities
        (provider_id, region_code, offer_type, available_from, available_until);

CREATE INDEX IF NOT EXISTS idx_library_user_status
    ON user_movie_library (user_id, watch_status);

CREATE INDEX IF NOT EXISTS idx_library_user_wishlist
    ON user_movie_library (user_id)
    WHERE is_wishlisted = TRUE;

CREATE INDEX IF NOT EXISTS idx_reviews_movie_active
    ON movie_reviews (movie_id, created_at DESC)
    WHERE deleted_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_ranking_snapshot_lookup
    ON ranking_snapshots
        (provider_id, region_code, ranking_type, ranking_date DESC);

CREATE INDEX IF NOT EXISTS idx_recommendation_runs_user
    ON recommendation_runs (user_id, recommendation_type, generated_at DESC);

CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

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

DROP TRIGGER IF EXISTS trg_users_updated_at ON users;
CREATE TRIGGER trg_users_updated_at
BEFORE UPDATE ON users
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

DROP TRIGGER IF EXISTS trg_auth_accounts_updated_at ON auth_accounts;
CREATE TRIGGER trg_auth_accounts_updated_at
BEFORE UPDATE ON auth_accounts
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

DROP TRIGGER IF EXISTS trg_movies_updated_at ON movies;
CREATE TRIGGER trg_movies_updated_at
BEFORE UPDATE ON movies
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

DROP TRIGGER IF EXISTS trg_user_movie_library_updated_at ON user_movie_library;
CREATE TRIGGER trg_user_movie_library_updated_at
BEFORE UPDATE ON user_movie_library
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

DROP TRIGGER IF EXISTS trg_movie_reviews_updated_at ON movie_reviews;
CREATE TRIGGER trg_movie_reviews_updated_at
BEFORE UPDATE ON movie_reviews
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

INSERT INTO ott_providers (code, name)
VALUES
    ('NETFLIX', '넷플릭스'),
    ('TVING', '티빙'),
    ('WAVVE', '웨이브'),
    ('DISNEY_PLUS', '디즈니+'),
    ('COUPANG_PLAY', '쿠팡플레이'),
    ('WATCHA', '왓챠'),
    ('APPLE_TV_PLUS', 'Apple TV+')
ON CONFLICT (code) DO NOTHING;

INSERT INTO genres (code, name)
VALUES
    ('ACTION', '액션'),
    ('ADVENTURE', '모험'),
    ('ANIMATION', '애니메이션'),
    ('COMEDY', '코미디'),
    ('CRIME', '범죄'),
    ('DOCUMENTARY', '다큐멘터리'),
    ('DRAMA', '드라마'),
    ('FAMILY', '가족'),
    ('FANTASY', '판타지'),
    ('HISTORY', '역사'),
    ('HORROR', '공포'),
    ('MUSIC', '음악'),
    ('MYSTERY', '미스터리'),
    ('ROMANCE', '로맨스'),
    ('SF', 'SF'),
    ('THRILLER', '스릴러'),
    ('WAR', '전쟁'),
    ('WESTERN', '서부')
ON CONFLICT (code) DO NOTHING;

COMMIT;
