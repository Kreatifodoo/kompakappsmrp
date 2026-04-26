"""Alembic environment — async, autogenerate-aware."""
import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from app.config import settings
from app.core.database import Base

# Import all models so Alembic sees them for autogenerate
from app.modules.identity import models as _identity_models  # noqa: F401
from app.modules.accounting import models as _accounting_models  # noqa: F401
from app.modules.sales import models as _sales_models  # noqa: F401
from app.modules.purchase import models as _purchase_models  # noqa: F401
from app.modules.payments import models as _payments_models  # noqa: F401
from app.modules.audit import models as _audit_models  # noqa: F401

config = context.config
config.set_main_option("sqlalchemy.url", settings.DB_PRIMARY_URL)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=settings.DB_PRIMARY_URL,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=True,
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
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
