"""
Скрипт для діагностики та фіксу таблиці user_follows
Використання: python fix_follows_table.py [--fix]
"""
import sys
from app import app
from db import db
from sqlalchemy import text

def diagnose():
    """Діагностика поточного стану таблиці"""
    with app.app_context():
        print("\n=== Діагностика user_follows ===\n")
        
        try:
            # Отримати структуру таблиці
            result = db.session.execute(text("SELECT * FROM user_follows LIMIT 0"))
            columns = list(result.keys())
            print(f"✅ Таблиця існує. Колонки: {columns}")
            
            # Перевірити чи є правильні колонки
            has_follower = 'follower_id' in columns
            has_author = 'author_id' in columns
            
            if has_follower and has_author:
                print("✅ Колонки follower_id та author_id присутні")
            else:
                print(f"❌ ПРОБЛЕМА: Очікуємо follower_id та author_id")
                print(f"   Знайдено: {columns}")
                return False
            
            # Показати приклади даних
            rows = db.session.execute(
                text("SELECT id, follower_id, author_id FROM user_follows LIMIT 10")
            ).fetchall()
            
            print(f"\n📊 Перші 10 записів (всього: {len(rows)}):")
            print(f"{'ID':<6} {'Follower':<10} {'Author':<10}")
            print("-" * 30)
            for r in rows:
                print(f"{r.id:<6} {r.follower_id:<10} {r.author_id:<10}")
            
            # Підрахунок статистики
            stats = db.session.execute(text("""
                SELECT 
                    COUNT(*) as total,
                    COUNT(DISTINCT follower_id) as unique_followers,
                    COUNT(DISTINCT author_id) as unique_authors
                FROM user_follows
            """)).fetchone()
            
            print(f"\n📈 Статистика:")
            print(f"   Всього записів: {stats.total}")
            print(f"   Унікальних follower_id: {stats.unique_followers}")
            print(f"   Унікальних author_id: {stats.unique_authors}")
            
            # Перевірка дублікатів
            dupes = db.session.execute(text("""
                SELECT follower_id, author_id, COUNT(*) as cnt
                FROM user_follows
                GROUP BY follower_id, author_id
                HAVING COUNT(*) > 1
            """)).fetchall()
            
            if dupes:
                print(f"\n⚠️  Знайдено {len(dupes)} дублікатів:")
                for d in dupes[:5]:
                    print(f"   follower={d.follower_id}, author={d.author_id}, count={d.cnt}")
            else:
                print("\n✅ Дублікатів не знайдено")
            
            return True
            
        except Exception as e:
            print(f"❌ Помилка: {e}")
            return False


def fix_table():
    """Очистити дублікати та пересоздати індекси"""
    with app.app_context():
        print("\n=== Фікс таблиці user_follows ===\n")
        
        try:
            # Видалити дублікати (залишити лише найстаріший запис)
            dialect = db.session.get_bind().dialect.name
            
            if dialect == "postgresql":
                print("🔧 Видалення дублікатів (PostgreSQL)...")
                db.session.execute(text("""
                    DELETE FROM user_follows
                    WHERE id NOT IN (
                        SELECT MIN(id)
                        FROM user_follows
                        GROUP BY follower_id, author_id
                    )
                """))
            else:
                # SQLite
                print("🔧 Видалення дублікатів (SQLite)...")
                db.session.execute(text("""
                    DELETE FROM user_follows
                    WHERE rowid NOT IN (
                        SELECT MIN(rowid)
                        FROM user_follows
                        GROUP BY follower_id, author_id
                    )
                """))
            
            db.session.commit()
            print("✅ Дублікати видалено")
            
            # Пересоздати індекси
            print("🔧 Пересоздання індексів...")
            
            # Видалити старі індекси якщо є
            try:
                db.session.execute(text("DROP INDEX IF EXISTS uq_user_follows_pair"))
                db.session.execute(text("DROP INDEX IF EXISTS ix_user_follows_follower"))
                db.session.execute(text("DROP INDEX IF EXISTS ix_user_follows_author"))
            except:
                pass
            
            # Створити нові
            db.session.execute(text("""
                CREATE UNIQUE INDEX IF NOT EXISTS uq_user_follows_pair
                ON user_follows (follower_id, author_id)
            """))
            db.session.execute(text("""
                CREATE INDEX IF NOT EXISTS ix_user_follows_follower
                ON user_follows (follower_id)
            """))
            db.session.execute(text("""
                CREATE INDEX IF NOT EXISTS ix_user_follows_author
                ON user_follows (author_id)
            """))
            
            db.session.commit()
            print("✅ Індекси створено")
            
            print("\n✅ Фікс завершено успішно!")
            
        except Exception as e:
            db.session.rollback()
            print(f"❌ Помилка при фіксі: {e}")
            return False
        
        return True


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--fix":
        # Спочатку діагностика
        if diagnose():
            print("\n" + "="*50)
            answer = input("\n⚠️  Виконати фікс? (yes/no): ")
            if answer.lower() in ['yes', 'y']:
                fix_table()
                print("\nПовторна діагностика після фіксу:")
                diagnose()
            else:
                print("Фікс скасовано")
    else:
        # Тільки діагностика
        diagnose()
        print("\n💡 Підказка: використайте --fix для автоматичного виправлення проблем")
