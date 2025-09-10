import sqlite3

# створюємо або відкриваємо файл database.db
conn = sqlite3.connect("database.db")
c = conn.cursor()

# створення таблиці users
c.execute("""
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT UNIQUE NOT NULL,
    name TEXT,
    avatar TEXT,
    bio TEXT,
    pxp INTEGER DEFAULT 0,
    name_changes INTEGER DEFAULT 0,
    password TEXT NOT NULL
)
""")

conn.commit()
conn.close()

print("База даних створена ✅")
