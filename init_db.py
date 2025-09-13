import sqlite3, os

# шлях до БД з Railway (ENV: DB_PATH=/data/database.db)
DB_PATH = os.environ.get("DB_PATH", "/data/database.db")

conn = sqlite3.connect(DB_PATH)
c = conn.cursor()

# створення або оновлення таблиці users
c.execute("""
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT UNIQUE NOT NULL,
    name TEXT,
    avatar TEXT,
    bio TEXT,
    pxp INTEGER DEFAULT 0,
    name_changes INTEGER DEFAULT 0,
    password TEXT NOT NULL,
    login_code TEXT UNIQUE
)
""")

# створюємо унікальні індекси (якщо їх ще немає)
c.execute("CREATE UNIQUE INDEX IF NOT EXISTS ux_users_email ON users(email)")
c.execute("CREATE UNIQUE INDEX IF NOT EXISTS ux_users_login_code ON users(login_code)")

conn.commit()
conn.close()

print("✅ Таблиця users готова. Поле login_code додано.")

