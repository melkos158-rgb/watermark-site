# Діагностика проблеми з Follow/Unfollow

## Проблема
Після натискання Follow кнопка скидається після F5, хоча підписка має зберігатися.

## Структура таблиці (правильна)
```sql
CREATE TABLE user_follows (
    id BIGINT PRIMARY KEY,
    follower_id INTEGER NOT NULL,  -- хто підписується (current user)
    author_id INTEGER NOT NULL,     -- на кого підписуються (target author)
    created_at TIMESTAMP NOT NULL
)
```

## Діагностика

### 1. Використати debug endpoint (в debug mode)
```bash
# В браузері:
GET http://localhost:5000/api/debug/follows
```

Цей endpoint покаже:
- Поточні підписки користувача
- Структуру таблиці
- Приклади даних

### 2. Використати скрипт діагностики
```bash
# Тільки діагностика (безпечно)
python fix_follows_table.py

# Діагностика + автоматичний фікс дублікатів
python fix_follows_table.py --fix
```

### 3. Переглянути логи (в debug mode)
При натисканні Follow в логах має з'явитися:
```
POST /api/follow/3: user 1 -> author 3
GET /api/user/follows for user 1: [{'followed_id': 3}]
GET /api/user/3/mini: followers_count = 1
```

### 4. Прямий SQL запит
```sql
-- Показати підписки користувача 1
SELECT * FROM user_follows WHERE follower_id = 1;

-- Очікуваний результат:
-- follower_id=1, author_id=3 (НЕ навпаки!)
```

## Можливі причини проблеми

### 1. Старі дані з неправильною структурою
**Симптом:** В БД follower_id та author_id переплутані
**Рішення:** Виконати міграцію даних
```sql
-- Створити нову таблицю
CREATE TABLE user_follows_new AS 
SELECT id, author_id as follower_id, follower_id as author_id, created_at
FROM user_follows;

-- Видалити стару
DROP TABLE user_follows;

-- Перейменувати
ALTER TABLE user_follows_new RENAME TO user_follows;
```

### 2. Кешування на фронтенді
**Симптом:** API повертає правильні дані, але JS не оновлюється
**Рішення:** Ctrl+Shift+R (hard reload) в браузері

### 3. Проблема з сесією
**Симптом:** session.get("user_id") повертає None або інше значення
**Рішення:** Перевірити логіни, куки

## Перевірка логіки endpoints

### GET /api/user/follows
```python
# ✅ Правильно:
SELECT author_id FROM user_follows WHERE follower_id = :current_user_id
# Повертає IDs авторів на яких підписаний поточний користувач
```

### POST /api/follow/<author_id>
```python
# ✅ Правильно:
INSERT INTO user_follows (follower_id, author_id) 
VALUES (:current_user_id, :author_id)
# follower_id = я, author_id = на кого підписуюсь
```

### GET /api/user/<id>/mini
```python
# ✅ Правильно:
SELECT COUNT(*) FROM user_follows WHERE author_id = :user_id
# Рахує скільки людей підписано на цього автора
```

## Очікувана поведінка після фіксу

1. **Follow на author_id=3:**
   - POST запит успішний
   - В БД: `follower_id=1, author_id=3`

2. **GET /api/user/follows:**
   - Повертає: `{"follows": [{"followed_id": 3}]}`

3. **F5 (reload):**
   - JS читає follows: `[3]`
   - `isFollowing = [3].includes(3)` → `true`
   - Кнопка показує "Following" ✅

4. **GET /api/user/3/mini:**
   - `followers_count = 1` (або більше)

## Файли змінені

1. **market.py** - додано:
   - Debug логування у всіх follow endpoints
   - `/api/debug/follows` - діагностичний endpoint

2. **fix_follows_table.py** - новий файл:
   - Діагностика структури таблиці
   - Автоматичне виправлення дублікатів
   - Пересоздання індексів

3. **debug_follows.sql** - SQL запити для ручної діагностики

## Як використовувати в продакшні

1. Увімкнути `debug=True` тимчасово
2. Відкрити `/api/debug/follows` в браузері
3. Зберегти вивід
4. Вимкнути debug mode
5. Проаналізувати дані

Або просто використати `fix_follows_table.py` локально на копії БД.
