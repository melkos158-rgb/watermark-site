-- Debug script для перевірки user_follows таблиці

-- 1. Показати всі записи в таблиці
SELECT * FROM user_follows ORDER BY created_at DESC LIMIT 20;

-- 2. Показати з іменами користувачів (якщо є таблиця users)
SELECT 
    uf.id,
    uf.follower_id,
    u1.name as follower_name,
    uf.author_id,
    u2.name as author_name,
    uf.created_at
FROM user_follows uf
LEFT JOIN users u1 ON uf.follower_id = u1.id
LEFT JOIN users u2 ON uf.author_id = u2.id
ORDER BY uf.created_at DESC
LIMIT 20;

-- 3. Підрахунок підписників для кожного автора
SELECT 
    author_id,
    u.name as author_name,
    COUNT(*) as followers_count
FROM user_follows uf
LEFT JOIN users u ON uf.author_id = u.id
GROUP BY author_id, u.name
ORDER BY followers_count DESC;

-- 4. Список авторів на яких підписаний конкретний користувач (замість 1 підставте свій user_id)
SELECT 
    uf.author_id,
    u.name as author_name
FROM user_follows uf
LEFT JOIN users u ON uf.author_id = u.id
WHERE uf.follower_id = 1;

-- 5. Перевірка наявності дублікатів
SELECT follower_id, author_id, COUNT(*) as cnt
FROM user_follows
GROUP BY follower_id, author_id
HAVING COUNT(*) > 1;
