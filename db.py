# db.py
import os
import sqlite3
from flask import g

# ===== Опційний Postgres =====
PSQL_URL = os.getenv("DATABASE_URL")
if PSQL_URL:
    import psycopg2
    import psycopg2.extras

DB_PATH = os.getenv("DB_PATH", "database.db")

# ---- Адаптер для Postgres, щоб виглядало як sqlite3.Connection ----
class _PsqlAdapter:
    def __init__(self, conn):
        self._conn = conn

    def _convert_qmarks(self, sql: str) -> str:
        # заміна всіх '?' на '%s' (простий випадок під наші запити)
        return sql.replace("?", "%s")

    def execute(self, sql, params=()):
        sql_psql = self._convert_qmarks(sql)
        cur = self._conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(sql_psql, params)
        return cur

    def commit(self):
        self._conn.commit()

    def close(self):
        try:
            self._conn.close()
        except Exception:
            pass


# ===== Ініціалізація таблиць =====
def _ensure_users_table(db, engine: str):
    try:
        if engine == "psql":
            db.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id SERIAL PRIMARY KEY,
                    email TEXT UNIQUE NOT NULL,
                    name TEXT,
                    avatar TEXT,
                    bio TEXT,
                    pxp INTEGER DEFAULT 0,
                    name_changes INTEGER DEFAULT 0,
                    password TEXT NOT NULL,
                    login_code TEXT
                )
            """)
            # індекс на login_code (може бути NULL, але має бути унікальним, коли не NULL)
            try:
                db.execute("CREATE UNIQUE INDEX IF NOT EXISTS ux_users_login_code ON users(login_code)")
            except Exception:
                # для старих PG без IF NOT EXISTS
                try:
                    db.execute("CREATE UNIQUE INDEX ux_users_login_code ON users(login_code)")
                except Exception:
                    pass
            db.commit()
        else:
            db.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    email TEXT UNIQUE NOT NULL,
                    name TEXT,
                    avatar TEXT,
                    bio TEXT,
                    pxp INTEGER DEFAULT 0,
                    name_changes INTEGER DEFAULT 0,
                    password TEXT NOT NULL,
                    login_code TEXT
                )
            """)
            db.execute("CREATE UNIQUE INDEX IF NOT EXISTS ux_users_login_code ON users(login_code)")
            db.commit()
    except Exception:
        # не валимо додаток, просто пропускаємо
        pass


def _ensure_messages_table(db, engine: str):
    try:
        if engine == "psql":
            db.execute("""
                CREATE TABLE IF NOT EXISTS messages (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER,
                    user_name TEXT,
                    user_email TEXT,
                    text TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            db.execute("CREATE INDEX IF NOT EXISTS ix_messages_created ON messages(created_at)")
            db.commit()
        else:
            db.execute("""
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    user_name TEXT,
                    user_email TEXT,
                    text TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            db.execute("CREATE INDEX IF NOT EXISTS ix_messages_created ON messages(created_at)")
            db.commit()
    except Exception:
        pass


def _ensure_schema(db, engine: str):
    _ensure_users_table(db, engine)
    _ensure_messages_table(db, engine)


# ===== Публічні функції =====
def get_db():
    """
    Повертає об'єкт під БД з API, подібним до sqlite:
      db.execute(sql, params).fetchone()/fetchall()
      db.commit()
    З'єднання кешується у flask.g на час запиту.
    """
    if "db_conn" in g and "db_engine" in g and g.db_conn:
        return g.db_conn

    if PSQL_URL:
        conn = psycopg2.connect(PSQL_URL)
        db = _PsqlAdapter(conn)
        g.db_conn = db
        g.db_engine = "psql"
        _ensure_schema(db, "psql")
        return db

    # SQLite (дефолт)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    g.db_conn = conn
    g.db_engine = "sqlite"
    _ensure_schema(conn, "sqlite")
    return conn


def close_db(exception=None):
    """
    Закриває з'єднання після запиту (викликається через app.teardown_appcontext).
    """
    db = g.pop("db_conn", None)
    engine = g.pop("db_engine", None)
    if db is None:
        return
    try:
        if engine == "psql" and isinstance(db, _PsqlAdapter):
            db.close()
        else:
            db.close()
    except Exception:
        pass


def ensure_login_code_column():
    """
    Гарантує наявність колонки users.login_code та унікального індексу.
    Використовується з auth/profile для входу по коду.
    """
    db = get_db()
    try:
        if PSQL_URL:
            # перевірка наявності колонки в Postgres
            row = db.execute(
                "SELECT column_name FROM information_schema.columns WHERE table_name=%s AND column_name=%s",
                ("users", "login_code"),
            ).fetchone()
            has_col = bool(row)
        else:
            # SQLite
            cols = db.execute("PRAGMA table_info(users)").fetchall()
            names = []
            for c in cols:
                if isinstance(c, sqlite3.Row):
                    names.append(c["name"])
                else:
                    # (cid, name, type, notnull, dflt_value, pk)
                    names.append(c[1] if len(c) > 1 else None)
            has_col = "login_code" in names

        if not has_col:
            # додаємо колонку
            db.execute("ALTER TABLE users ADD COLUMN login_code TEXT")
            # індекс
            try:
                db.execute("CREATE UNIQUE INDEX IF NOT EXISTS ux_users_login_code ON users(login_code)")
            except Exception:
                try:
                    db.execute("CREATE UNIQUE INDEX ux_users_login_code ON users(login_code)")
                except Exception:
                    pass
            db.commit()
    except Exception:
        # не валимо застосунок
        pass
