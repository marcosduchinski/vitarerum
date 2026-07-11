from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context
from app.ai.museum_narrative.infrastructure import (
    models as museum_narrative_models,  # noqa: F401
)
from app.ai.museum_question_triage.infrastructure import (
    models as museum_question_triage_models,  # noqa: F401
)
from app.cidoc_crm.in_situ_visit_mapping.infrastructure import (
    models as in_situ_visit_models,  # noqa: F401
)
from app.collection_object_index.infrastructure import (
    models as collection_object_index_models,  # noqa: F401
)
from app.config import settings
from app.database import Base
from app.document_templates.infrastructure import (
    models as document_templates_models,  # noqa: F401
)
from app.identity.infrastructure import (
    models as identity_models,  # noqa: F401
)
from app.museum_questions.infrastructure import (
    models as museum_questions_models,  # noqa: F401
)
from app.public_submission.infrastructure import (
    models as public_submission_models,  # noqa: F401
)
from app.reports.in_situ_visit.infrastructure import (
    models as in_situ_visit_report_models,  # noqa: F401
)
from app.use_of_collections.infrastructure import (
    models as use_of_collections_models,  # noqa: F401
)

config = context.config
config.set_main_option("sqlalchemy.url", settings.database_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def include_object(object_, name, type_, reflected, compare_to) -> bool:
    """Keep PostgreSQL-only search artifacts out of autogenerate drift checks."""
    if type_ == "column" and reflected and compare_to is None:
        if object_.table.name == "collection_index_object" and name == "tsv":
            return False
    if type_ == "index" and reflected and compare_to is None:
        if name in {
            "ix_collection_index_object_content_trgm",
            "ix_collection_index_object_tsv",
        }:
            return False
    return True


def compare_type(
    context,
    inspected_column,
    metadata_column,
    inspected_type,
    metadata_type,
):
    if (
        inspected_column.table.name == "collection_index_object"
        and inspected_column.name == "cells"
    ):
        return False
    return None


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_object=include_object,
        compare_type=compare_type,
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        include_object=include_object,
        compare_type=compare_type,
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    import asyncio

    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
