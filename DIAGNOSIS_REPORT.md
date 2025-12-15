# 🔍 ДІАГНОСТИКА: Follow кнопка скидається після F5

## ✅ Результати перевірки

### 1️⃣ Template для /market?author_id=3
**Файл:** `templates/market/index.html`  
**Роут:** `@bp.get("/market")` → `page_market()` в market.py:729

**Код передачі author_id:**
```python
author_id = _parse_int(request.args.get("author_id"), 0)
return render_template("market/index.html", author_id=author_id or None)
```

### 2️⃣ JS файли та логіка Follow

#### А) Author Header (inline script в index.html)
**Місце:** templates/market/index.html lines 381-507  
**Кнопка:** `#authorFollowBtn` (без class `follow-btn`)  
**Логіка:** ✅ ПРАВИЛЬНА

```javascript
// Lines 433-450: Завантаження статусу
const followsResp = await fetch('/api/user/follows');
const followsData = await followsResp.json();
const followIds = followsRaw.map(x => {
  if (typeof x === "number") return x;
  if (x && typeof x === "object") return Number(x.followed_id ?? x.author_id ?? x.id);
  return NaN;
}).filter(n => Number.isFinite(n));

isFollowing = followIds.includes(authorId); // ✅ Правильно!
```

#### Б) Follow.js (для item cards в detail.html)
**Файл:** static/market/js/follow.js  
**Селектор:** `.follow-btn` (НЕ #authorFollowBtn)  
**Логіка:** ❌ Застарілий endpoint

```javascript
// Line 34: Використовує інший endpoint
const res = await fetch(`/api/follow/status/${authorId}`);
```

**Висновок:** follow.js НЕ конфліктує з author header (різні селектори).

### 3️⃣ Всі endpoints /api/follow/*

#### Знайдено в market.py:
1. `@bp.get("/api/user/follows")` - line 1435  
   - Повертає список `[{followed_id: X}, ...]`  
   - Використовується: index.html inline script ✅, top_prints.js ✅

2. `@bp.get("/api/follow/status/<int:author_id>")` - line 1467  
   - Повертає `{following: true/false}` для конкретного автора  
   - Використовується: follow.js (тільки в detail.html)

3. `@bp.post("/api/follow/<int:author_id>")` - line 1488  
   - INSERT follower_id=current_user, author_id=param ✅  
   - Повертає `{ok, following, followers_count}`

4. `@bp.delete("/api/follow/<int:author_id>")` - line 1530  
   - DELETE WHERE follower_id=current_user AND author_id=param ✅  
   - Повертає `{ok, following, followers_count}`

**Дублів немає** - кожен endpoint унікальний.

### 4️⃣ Перевірка followers_count

**Код підрахунку** в `/api/user/<id>/mini` (line 1403):
```python
follower_count = db.session.execute(
    text("SELECT COUNT(*) FROM user_follows WHERE author_id = :uid"),
    {"uid": user_id}
).scalar() or 0
```

✅ **Правильно** - рахує по author_id

---

## 🎯 ВИСНОВОК

### Код ідеальний, проблема не в коді!

**Author header кнопка** (`#authorFollowBtn`) використовує:
- ✅ `/api/user/follows` для завантаження статусу
- ✅ `/api/follow/<id>` POST/DELETE для toggle
- ✅ Robust parsing з підтримкою різних форматів
- ✅ Правильна логіка `followIds.includes(authorId)`

**Можливі причини проблеми:**

### 🔍 Перевірка 1: Network tab після F5
```
1. F5 на /market?author_id=3
2. Відкрити DevTools → Network
3. Знайти запит: GET /api/user/follows
4. Подивитися Response
```

**Очікувано:** `{"ok": true, "follows": [{"followed_id": 3}]}`  
**Якщо порожнє:** `{"ok": true, "follows": []}` - проблема в БД/сесії!

### 🔍 Перевірка 2: Сесія
```javascript
// В Console браузера:
fetch('/api/user/follows').then(r => r.json()).then(console.log)
```

**Якщо 401 або follows: []** → session.get("user_id") не працює після F5

### 🔍 Перевірка 3: База даних
```bash
# На Railway або локально:
python fix_follows_table.py

# Або відкрити /api/debug/follows (в debug mode)
```

**Очікувано:** Запис `follower_id=<YOUR_ID>, author_id=3` існує в таблиці

### 🔍 Перевірка 4: Кеш браузера
- Ctrl+Shift+R (hard reload)
- Або Incognito mode

---

## 📋 Next Steps

### Якщо Network показує follows: []
→ Проблема в БД або POST не зберігає дані

**Перевірити:**
```python
# В Railway console або локально:
python -c "
from app import app
from db import db
from sqlalchemy import text

with app.app_context():
    # Показати всі підписки
    rows = db.session.execute(text('SELECT * FROM user_follows')).fetchall()
    for r in rows:
        print(f'follower_id={r.follower_id}, author_id={r.author_id}')
"
```

### Якщо Network показує follows: [{"followed_id": 3}]
→ Проблема у фронтенді (не той authorId або кеш)

**Перевірити:**
```javascript
// В Console після F5:
const header = document.getElementById('authorProfileHeader');
console.log('authorId from Jinja:', {{ author_id }});
console.log('authorId from URL:', new URLSearchParams(location.search).get('author_id'));
```

---

## 🛠️ Швидкий фікс якщо followers_count не оновлюється

Це **окрема проблема** від кнопки Follow.

**Можливі причини:**
1. Replica lag на Railway (читання зі старої репліки)
2. Кеш на CDN/proxy
3. Транзакція не закомітилась

**Перевірка:**
```bash
# Прямий запит після Follow:
curl https://your-app.railway.app/api/user/3/mini

# Очікувано: "followers_count": 1 (або більше)
```

Якщо все ще 0 → проблема в БД (INSERT не спрацював або COUNT рахує не там).
