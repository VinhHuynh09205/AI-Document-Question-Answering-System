from dataclasses import dataclass

import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT


@dataclass(slots=True)
class PgConfig:
    host: str
    port: int
    user: str
    password: str
    database: str


def ensure_database(config: PgConfig) -> None:
    conn = psycopg2.connect(
        host=config.host, port=config.port, user=config.user,
        password=config.password, dbname="postgres",
    )
    conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT 1 FROM pg_database WHERE datname = %s", (config.database,)
            )
            if not cursor.fetchone():
                cursor.execute(f'CREATE DATABASE "{config.database}"')
    finally:
        conn.close()


def connect(config: PgConfig):
    return psycopg2.connect(
        host=config.host, port=config.port, user=config.user,
        password=config.password, dbname=config.database,
    )
