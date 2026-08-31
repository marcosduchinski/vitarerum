-- Seed de identidade do MUHNAC.
--
-- Recria do zero a instituicao, os usuarios, os grupos e as permissoes. E'
-- idempotente: apaga tudo antes de inserir, entao pode ser reaplicado.
--
-- Aplicar com:
--   psql -U vitarerum -d vitarerum < scripts/seed.sql
-- ou, no ambiente provisionado:
--   APPLY_DEV_SEED=yes STEP=seed ./deploy/provision.sh
--
-- Os enderecos de e-mail sao reais e intencionais: as comunicacoes do sistema
-- (confirmacao de submissao publica, reset de senha, notificacoes de direcao)
-- precisam chegar a uma caixa que se possa abrir para acompanhar o fluxo.
--
-- A senha das duas contas e' a mesma, definida pelo hash bcrypt abaixo.

BEGIN;

-- Nenhuma das chaves estrangeiras tem ON DELETE CASCADE (todas sao NO ACTION),
-- entao a ordem importa: primeiro o que referencia, depois o que e'
-- referenciado. identity_users entra na limpeza porque identity_users.email e'
-- UNIQUE - sem apagar, reinserir Bob e Carla violaria a restricao.
DELETE FROM public.identity_permissions;
DELETE FROM public.identity_groups;
DELETE FROM public.identity_institutions;
DELETE FROM public.identity_users;

DO $$
DECLARE
    v_institution_id UUID := gen_random_uuid();

    v_bob_id   UUID := gen_random_uuid();
    v_carla_id UUID := gen_random_uuid();

    v_default_password_hash TEXT :=
        '$2b$12$HCAWMD5i1RBxfKDCADXc5.vG8/fCdcZJ3afbgZKF596sPQHTCSdye';

    v_external_group_id               TEXT := 'grp-ext';
    v_direction_group_id              TEXT := 'grp-dir';
    v_curatorial_group_id             TEXT := 'grp-cur';
    v_collections_management_group_id TEXT := 'grp-cm';
    v_sys_admin_group_id              TEXT := 'grp-sys-adm';

BEGIN

    -- =====================================================
    -- Instituição
    -- =====================================================

    INSERT INTO public.identity_institutions (
        id,
        "name",
        email,
        address,
        phone
    )
    VALUES (
        v_institution_id,
        'MUHNAC - Museu Nacional de História Natural e da Ciência de Lisboa',
        'vitarerum.collections@gmail.com',
        'Lisboa',
        ''
    );


    -- =====================================================
    -- Usuários
    -- =====================================================

    INSERT INTO public.identity_users (
        id,
        "name",
        email,
        password_hash
    )
    VALUES
        (
            v_bob_id,
            'Bob',
            'bob.curatorial.vita@outlook.com',
            v_default_password_hash
        ),
        (
            v_carla_id,
            'Carla',
            'carla.curatorial.vita@outlook.com',
            v_default_password_hash
        );


    -- =====================================================
    -- Grupos
    -- =====================================================

    INSERT INTO public.identity_groups (
        id,
        "name",
        institution_id
    )
    VALUES
        (
            v_external_group_id,
            'EXTERNAL'::public."identity_group_name",
            v_institution_id
        ),
        (
            v_curatorial_group_id,
            'CURATORIAL'::public."identity_group_name",
            v_institution_id
        ),
        (
            v_direction_group_id,
            'DIRECTION'::public."identity_group_name",
            v_institution_id
        ),
        (
            v_collections_management_group_id,
            'COLLECTIONS_MANAGEMENT'::public."identity_group_name",
            v_institution_id
        ),
        (
            v_sys_admin_group_id,
            'SYS_ADMIN'::public."identity_group_name",
            v_institution_id
        );


    -- =====================================================
    -- Permissões
    -- =====================================================

    INSERT INTO public.identity_permissions (
        id,
        user_id,
        group_id
    )
    VALUES
        -- Bob: curador
        (
            gen_random_uuid(),
            v_bob_id,
            v_curatorial_group_id
        ),

        -- Bob: gestor de coleções
        (
            gen_random_uuid(),
            v_bob_id,
            v_collections_management_group_id
        ),

        -- Bob: administrador do sistema
        (
            gen_random_uuid(),
            v_bob_id,
            v_sys_admin_group_id
        ),

        -- Carla: diretora
        (
            gen_random_uuid(),
            v_carla_id,
            v_direction_group_id
        ),

        -- Carla: curadora
        (
            gen_random_uuid(),
            v_carla_id,
            v_curatorial_group_id
        );

END
$$;

COMMIT;
