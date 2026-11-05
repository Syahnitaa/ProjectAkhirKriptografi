import pymysql
import config


def get_db():
    """Buka koneksi ke database MySQL."""
    return pymysql.connect(
        host=config.DB_HOST,
        user=config.DB_USER,
        password=config.DB_PASSWORD,
        database=config.DB_NAME,
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,  # hasil query berupa dictionary
    )
