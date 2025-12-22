import os

import psycopg2
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


def init_app_db(app):
    """
    Ініціалізація бази даних Proofly + створення таблиць якщо їх немає.
    Якщо потрібно повністю перезаписати таблиці — можна вставити DROP TABLE нижче.
    """

    # ---- URL бази з Railway
    db_url = os.environ.get("DATABASE_URL")
    if db_url and db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql://", 1)

    app.config["SQLALCHEMY_DATABASE_URI"] = db_url or "sqlite:///database.db"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    db.init_app(app)

    # ---- Підключення через psycopg2
    conn = psycopg2.connect(os.environ["DATABASE_URL"])
    cur = conn.cursor()

    # ---- Якщо хочеш очистити таблиці (раскоментуй ↓)
    # cur.execute("DROP TABLE IF EXISTS items;")
    # cur.execute("DROP TABLE IF EXISTS market_items;")
    # print("⚠️  Таблиці items та market_items видалено!")

    # ---- Створення таблиці USERS
    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id SERIAL PRIMARY KEY,
        email TEXT UNIQUE NOT NULL,
        name TEXT,
        avatar TEXT,
        bio TEXT,
        pxp INTEGER DEFAULT 0,
        name_changes INTEGER DEFAULT 0,
        password TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT NOW()
    );
    """)

    # ---- Створення таблиці ITEMS
    cur.execute("""
    CREATE TABLE IF NOT EXISTS items (
        id SERIAL PRIMARY KEY,
        title TEXT,
        description TEXT,
        price INTEGER DEFAULT 0,
        tags TEXT,
        cover_url TEXT,
        gallery_urls JSONB DEFAULT '[]',
        stl_main_url TEXT,
        stl_extra_urls JSONB DEFAULT '[]',
        zip_url TEXT,
        format TEXT DEFAULT 'stl',
        downloads INTEGER DEFAULT 0,
        user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
        created_at TIMESTAMP DEFAULT NOW(),
        updated_at TIMESTAMP DEFAULT NOW()
    );
    """)

    # ---- Створення таблиці MARKET_ITEMS (резервна, для маркету)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS market_items (
        id SERIAL PRIMARY KEY,
        user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
        title TEXT,
        price INTEGER DEFAULT 0,
        tags TEXT,
        desc TEXT,
        cover_url TEXT,
        gallery_urls JSONB DEFAULT '[]',
        stl_main_url TEXT,
        stl_extra_urls JSONB DEFAULT '[]',
        created_at TIMESTAMP DEFAULT NOW()
    );
    """)

    conn.commit()
    cur.close()
    conn.close()
    print("✅ Таблиці users, items та market_items перевірено або створено.")


if __name__ == "__main__":
    # --- Тимчасовий Flask app для ініціалізації
    from flask import Flask
    app = Flask(__name__)
    init_app_db(app)
