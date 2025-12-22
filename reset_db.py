from app import app
from db import db


def drop_specific_tables():
    with app.app_context():
        # список таблиць, які треба видалити
        target_tables = ["items", "market_items"]

        conn = db.engine.raw_connection()
        cur = conn.cursor()
        for table in target_tables:
            try:
                print(f"🗑 Видаляю таблицю: {table} ...")
                cur.execute(f"DROP TABLE IF EXISTS {table} CASCADE;")
            except Exception as e:
                print(f"⚠️ Помилка при видаленні {table}: {e}")
        conn.commit()
        cur.close()
        conn.close()
        print("✅ Таблиці items і market_items видалені!")

if __name__ == "__main__":
    drop_specific_tables()
