BEGIN;

DELETE FROM user_ott_subscriptions
WHERE provider_id IN (
    SELECT id FROM ott_providers WHERE code = 'COUPANG_PLAY'
);

DELETE FROM ott_availabilities
WHERE provider_id IN (
    SELECT id FROM ott_providers WHERE code = 'COUPANG_PLAY'
);

DELETE FROM ranking_snapshots
WHERE provider_id IN (
    SELECT id FROM ott_providers WHERE code = 'COUPANG_PLAY'
);

UPDATE recommendation_runs
SET provider_id = NULL
WHERE provider_id IN (
    SELECT id FROM ott_providers WHERE code = 'COUPANG_PLAY'
);

DELETE FROM ott_providers
WHERE code = 'COUPANG_PLAY';

COMMIT;
