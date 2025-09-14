import psycopg2
import os

DATABASE_URL = os.environ["DATABASE_URL"]

conn = psycopg2.connect(DATABASE_URL)
cur = conn.cursor()

cur.execute("""
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
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
cur.close()
conn.close()

print("✅ Таблиця users створена в PostgreSQL")

print("✅ Таблиця users готова. Поле login_code додано.")


