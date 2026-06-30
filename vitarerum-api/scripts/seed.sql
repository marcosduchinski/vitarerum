-- Bootstrap identity seed for local development / smoke testing.
--
-- The API has no bootstrap endpoint: every request needs an X-Permission-Id
-- header pointing at an existing identity_permissions row, and creating users
-- itself requires a SYS_ADMIN caller permission. So seed one initial admin
-- permission here before calling the API.
--
-- Apply with:
--   docker compose exec -T postgres psql -U vitarerum -d vitarerum < scripts/seed.sql
--
-- Permission ids created:
--   perm-sys-admin (SYS_ADMIN bootstrap administrator)
--   perm-ext       (EXTERNAL requester)
--   perm-cur       (CURATORIAL staff)
--
-- Seeded login: all users have the password "password" (bcrypt hash below).
-- Log in via POST /auth/login to obtain a Bearer token, then send it together
-- with X-Permission-Id on every other request.

INSERT INTO identity_users (id, name, email, password_hash) VALUES
  ('c03639c9-ebf3-44ed-89d3-e067f70de914', 'System Administrator', 'admin@museum.pt', '$2b$12$MviuKDF31uPO5VtEfHQj9urZuNTC9XPB3Jp3Aj79wvniHOtfI/x8a'),
  ('c03639c9-ebf3-44ed-89d3-e067f70de915', 'Researcher', 'researcher@uni.pt', '$2b$12$MviuKDF31uPO5VtEfHQj9urZuNTC9XPB3Jp3Aj79wvniHOtfI/x8a'),
  ('c03639c9-ebf3-44ed-89d3-e067f70de916', 'Curator',        'curator@museum.pt', '$2b$12$MviuKDF31uPO5VtEfHQj9urZuNTC9XPB3Jp3Aj79wvniHOtfI/x8a'),
  ('c03639c9-ebf3-44ed-89d3-e067f70de917', 'Collection Manager',        'manager@museum.pt', '$2b$12$MviuKDF31uPO5VtEfHQj9urZuNTC9XPB3Jp3Aj79wvniHOtfI/x8a')
ON CONFLICT (id) DO NOTHING;

-- Every group belongs to an institution (see migration 0001_add_institutions).
-- This id matches DEFAULT_INSTITUTION_ID in that migration.
INSERT INTO identity_institutions (id, name, email, address, phone)
VALUES ('a0000000-0000-0000-0000-000000000001', 'MUHNAC', '', '', '')
ON CONFLICT (id) DO NOTHING;

INSERT INTO identity_groups (id, name, institution_id)
SELECT 'grp-ext', 'EXTERNAL', 'a0000000-0000-0000-0000-000000000001'
WHERE NOT EXISTS (SELECT 1 FROM identity_groups WHERE name = 'EXTERNAL')
ON CONFLICT (id) DO UPDATE SET name = EXCLUDED.name;

INSERT INTO identity_groups (id, name, institution_id)
SELECT 'grp-cur', 'CURATORIAL', 'a0000000-0000-0000-0000-000000000001'
WHERE NOT EXISTS (SELECT 1 FROM identity_groups WHERE name = 'CURATORIAL')
ON CONFLICT (id) DO UPDATE SET name = EXCLUDED.name;

INSERT INTO identity_groups (id, name, institution_id)
SELECT 'grp-col', 'COLLECTIONS_MANAGEMENT', 'a0000000-0000-0000-0000-000000000001'
WHERE NOT EXISTS (
  SELECT 1 FROM identity_groups WHERE name = 'COLLECTIONS_MANAGEMENT'
)
ON CONFLICT (id) DO UPDATE SET name = EXCLUDED.name;

INSERT INTO identity_groups (id, name, institution_id)
SELECT 'grp-dir', 'DIRECTION', 'a0000000-0000-0000-0000-000000000001'
WHERE NOT EXISTS (SELECT 1 FROM identity_groups WHERE name = 'DIRECTION')
ON CONFLICT (id) DO UPDATE SET name = EXCLUDED.name;

INSERT INTO identity_groups (id, name, institution_id)
SELECT 'grp-sys-admin', 'SYS_ADMIN', 'a0000000-0000-0000-0000-000000000001'
WHERE NOT EXISTS (SELECT 1 FROM identity_groups WHERE name = 'SYS_ADMIN')
ON CONFLICT (id) DO UPDATE SET name = EXCLUDED.name;

INSERT INTO identity_permissions (id, user_id, group_id) VALUES
  (
    'perm-sys-admin',
    'c03639c9-ebf3-44ed-89d3-e067f70de914',
    (SELECT id FROM identity_groups WHERE name = 'SYS_ADMIN' LIMIT 1)
  ),
  (
    'perm-ext',
    'c03639c9-ebf3-44ed-89d3-e067f70de915',
    (SELECT id FROM identity_groups WHERE name = 'EXTERNAL' LIMIT 1)
  ),
  (
    'perm-cur',
    'c03639c9-ebf3-44ed-89d3-e067f70de916',
    (SELECT id FROM identity_groups WHERE name = 'CURATORIAL' LIMIT 1)
  ),
  (
    'perm-col',
    'c03639c9-ebf3-44ed-89d3-e067f70de917',
    (SELECT id FROM identity_groups WHERE name = 'COLLECTIONS_MANAGEMENT' LIMIT 1)
  )
ON CONFLICT (id) DO NOTHING;
