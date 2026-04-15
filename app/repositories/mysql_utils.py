from dataclasses import dataclass

import pymysql


@dataclass(slots=True)
class MySqlConfig:
    host: str
    port: int
    user: str
    password: str
    database: str
    charset: str = "utf8mb4"


def ensure_database(config: MySqlConfig) -> None:
    conn = pymysql.connect(
        host=config.host,
        port=config.port,
        user=config.user,
        password=config.password,
        charset=config.charset,
        autocommit=True,
    )
    try:
        with conn.cursor() as cursor:
            safe_db_name = config.database.replace("`", "")
            cursor.execute(
                f"CREATE DATABASE IF NOT EXISTS `{safe_db_name}` CHARACTER SET {config.charset}"
            )
    finally:
        conn.close()


def connect(config: MySqlConfig):
    return pymysql.connect(
        host=config.host,
        port=config.port,
        user=config.user,
        password=config.password,
        database=config.database,
        charset=config.charset,
        autocommit=False,
    )
