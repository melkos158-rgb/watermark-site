# 🔍 Upload System Audit Report

## ✅ 1. attach_uploaded_files() - Database Write

**Файл:** [market_api.py](market_api.py#L494-L585)

### Перевірка присвоєнь:

**✅ Cover:**
```python
# Line 550-551
if data.get('cover_url'):
    item.cover_url = data['cover_url']
    current_app.logger.info(f"[ATTACH]   cover_url: {data['cover_url'][:80]}...")
```
- **Поле в БД:** `item.cover_url` ✅
- **Джерело:** `data['cover_url']` з JSON payload
- **Логування:** Так, перші 80 символів URL

**✅ STL:**
```python
# Line 541-543
if data.get('stl_url'):
    item.stl_main_url = data['stl_url']
    current_app.logger.info(f"[ATTACH]   stl_url: {data['stl_url'][:80]}...")
```
- **Поле в БД:** `item.stl_main_url` ✅
- **Джерело:** `data['stl_url']` з JSON payload
- **Логування:** Так, перші 80 символів URL

**✅ ZIP:**
```python
# Line 546-548
if data.get('zip_url'):
    item.zip_url = data['zip_url']
    current_app.logger.info(f"[ATTACH]   zip_url: {data['zip_url'][:80]}...")
```
- **Поле в БД:** `item.zip_url` ✅
- **Джерело:** `data['zip_url']` з JSON payload
- **Логування:** Так, перші 80 символів URL

**✅ Video:**
```python
# Line 535-537
if data.get('video_url'):
    item.video_url = data['video_url']
    item.video_duration = data.get('video_duration', 10)
```
- **Поле в БД:** `item.video_url` ✅

### Валідація:

```python
# Line 560-566
if not data.get('stl_url') and not data.get('zip_url'):
    current_app.logger.warning(f"[ATTACH] Cannot publish: missing both stl_url and zip_url")
    item.upload_status = 'failed'
    item.upload_progress = 0
    db.session.commit()
    return jsonify({"ok": False, "error": "missing_files"}), 400
```
- **Вимога:** Хоча б `stl_url` АБО `zip_url` ✅
- **Статус при помилці:** `'failed'` ✅

### Публікація:

```python
# Line 568-571
item.upload_progress = 100
item.upload_status = 'published'
item.is_published = True

db.session.commit()
```
- **Статус:** `'published'` ✅
- **Progress:** `100` ✅
- **is_published:** `True` ✅
- **Commit:** Так ✅

### Логування (для діагностики):

```python
# Line 514-520 - Вхідні дані
current_app.logger.info(
    f"[ATTACH] item={item_id} "
    f"cover={data.get('cover_url')} "
    f"stl={data.get('stl_url')} "
    f"zip={data.get('zip_url')} "
    f"video={data.get('video_url')}"
)

# Line 576 - Успішна публікація
current_app.logger.info(f"[ATTACH] Item {item_id} published successfully")
```

**✅ ВЕРДИКТ:** Attach правильно пише всі поля в БД з логуванням.

---

## ✅ 2. /api/items Endpoint - JSON Response

**Файл:** [market.py](market.py#L1161-L1320)

### Серіалізація через _item_to_dict():

**Функція:** [market.py#L460-L550](market.py#L460-L550)

```python
def _item_to_dict(it: Dict[str, Any]) -> Dict[str, Any]:
    # ...
    # Get cover from cover_url or cover field
    raw_cover = safe_get("cover_url") or safe_get("cover") or ""
    
    # ...
    
    # Normalize cover, fallback to first gallery image
    cover_url = _normalize_cover_url(raw_cover)
    if (not raw_cover or cover_url == COVER_PLACEHOLDER) and normalized_gallery:
        cover_url = normalized_gallery[0]
    
    return {
        # ...
        "cover_url": cover_url,  # ✅ Always normalized, never "no image"
        "gallery_urls": normalized_gallery,
        # ...
    }
```

### JSON Поля:

**✅ Основне поле:**
```python
"cover_url": cover_url  # ✅ Завжди нормалізоване
```

**Fallback логіка:**
1. Спочатку береться `cover_url` з БД
2. Якщо немає → fallback на `cover` (legacy)
3. Якщо немає → fallback на перше фото з gallery
4. Нормалізується через `_normalize_cover_url()`

**✅ ВЕРДИКТ:** 
- API віддає поле `cover_url` ✅
- З fallback на gallery якщо cover_url пустий ✅
- Завжди нормалізоване (не "no image") ✅

---

## ✅ 3. Templates - Використання Cover

### A) _item_card.html (картки на маркеті)

**Файл:** [templates/market/_item_card.html](templates/market/_item_card.html#L1-L80)

**Логіка вибору cover:**

```jinja2
{# Line 26-32 - Використання cover_url якщо є #}
{% if not cover and it.cover_url %}
  {% set cover = it.cover_url %}
{% endif %}
{% if not cover and it.cover %}
  {% set cover = it.cover %}
{% endif %}
```

**Нормалізація:**

```jinja2
{# Line 52-61 - Нормалізація (додає / якщо немає префіксу) #}
{% set cover_src = cover %}
{% if cover_src %}
  {% if cover_src is string %}
    {% if not cover_src.startswith('http://') 
        and not cover_src.startswith('https://') 
        and not cover_src.startswith('/') %}
      {% set cover_src = '/' ~ cover_src %}
    {% endif %}
  {% else %}
    {% set cover_src = None %}
  {% endif %}
{% endif %}
```

**⚠️ АНАЛІЗ:**
- Читає `it.cover_url` (правильно) ✅
- Fallback на `it.cover` (legacy) ✅
- **НЕ додає `/media/user_...` префікси** ✅
- Додає `/` тільки якщо URL відносний (не починається з `/`, `http://`, `https://`) ✅

**Для нового item з `cover_url="/api/market/media/35/cover_xxx.png"`:**
- `cover` = `/api/market/media/35/cover_xxx.png` ✅
- `cover_src` = `/api/market/media/35/cover_xxx.png` (без змін, бо починається з `/`) ✅
- `<img src="/api/market/media/35/cover_xxx.png">` ✅

**✅ ВЕРДИКТ:** Template не домальовує префікси для URLs з `/api/`

---

### B) detail.html (сторінка айтема)

**Файл:** [templates/market/detail.html](templates/market/detail.html#L218-L230)

**Логіка:**

```jinja2
{# Line 218 #}
{% set cover_src = item.cover_url or item.cover or (item.photos[0] if item.photos) %}

<div class="cover">
  <img src="{{ cover_src or '/static/img/placeholder_stl.jpg' }}"
       alt="{{ item.title }}"
       loading="lazy"
       onerror="this.onerror=null;this.src='/static/img/placeholder_stl.jpg'">
</div>
```

**⚠️ АНАЛІЗ:**
- Читає `item.cover_url` (правильно) ✅
- Fallback на `item.cover` → `item.photos[0]` ✅
- **НЕ додає жодних префіксів** ✅
- Прямо вставляє в `<img src="{{ cover_src }}">` ✅

**Для нового item з `cover_url="/api/market/media/35/cover_xxx.png"`:**
- `cover_src` = `/api/market/media/35/cover_xxx.png` ✅
- `<img src="/api/market/media/35/cover_xxx.png">` ✅

**✅ ВЕРДИКТ:** Template використовує URL as-is, без додаткових префіксів

---

### C) JavaScript (динамічний рендер)

**Файл:** [templates/market/detail.html](templates/market/detail.html#L1096)

```javascript
// Line 1096 - Related items render
<img src="${it.cover_url || '/static/img/placeholder_stl.jpg'}"
```

**✅ ВЕРДИКТ:** JS читає `it.cover_url` напряму з API

---

## 📊 Фінальний Вердикт

### ✅ Всі 3 контрольні точки PASSED:

**1. attach_uploaded_files() пише в БД:**
- ✅ `item.cover_url = data['cover_url']`
- ✅ `item.stl_main_url = data['stl_url']`
- ✅ `item.zip_url = data['zip_url']`
- ✅ `upload_status = 'published'` при наявності stl/zip
- ✅ `db.session.commit()` після всіх присвоєнь
- ✅ Логування всіх URLs

**2. /api/items віддає правильне поле:**
- ✅ JSON містить `"cover_url"` (не `cover` або `cover_src`)
- ✅ Fallback на gallery якщо cover_url пустий
- ✅ Завжди нормалізоване (не "no image")

**3. Templates не домальовують префікси:**
- ✅ `_item_card.html` читає `it.cover_url` напряму
- ✅ `detail.html` читає `item.cover_url` напряму
- ✅ JS читає `it.cover_url` з API
- ✅ НЕ додають `/media/user_...` для URLs з `/api/`
- ✅ `_as_is_or_legacy()` в models_market.py запобігає подвійним префіксам

---

## 🔥 Очікувані результати після deploy:

### Railway Logs:

```
[UPLOAD_SAVE] item=35 type=cover path=/data/market_uploads/market_items/35/cover_xxx.png exists=True size=123456
[ATTACH] item=35 cover=/api/market/media/35/cover_xxx.png stl=/api/market/media/35/stl_model.stl zip=None video=None
[ATTACH]   cover_url: /api/market/media/35/cover_xxx.png...
[ATTACH]   stl_url: /api/market/media/35/stl_model.stl...
[ATTACH] Item 35 published successfully
```

### Frontend:

**GET /api/items:**
```json
{
  "items": [
    {
      "id": 35,
      "title": "Test Model",
      "cover_url": "/api/market/media/35/cover_xxx.png",
      "url": "/api/market/media/35/stl_model.stl"
    }
  ]
}
```

**HTML на /market:**
```html
<img src="/api/market/media/35/cover_xxx.png" loading="lazy">
```

**Browser Network:**
```
GET /api/market/media/35/cover_xxx.png → 200 OK
GET /api/market/media/35/stl_model.stl → 200 OK
```

**Visual:**
- ✅ Картка має обкладинку (не "No image")
- ✅ STL відкривається в viewer на /item/35
- ✅ Кнопка Download працює

---

## 🎯 Залишилось тільки:

1. **Deploy до Railway**
2. **Завантажити тестову модель** (STL + cover)
3. **Перевірити logs** на наявність правильних шляхів
4. **Відкрити /item/35** → STL має завантажитись
5. **Відкрити /market** → картка має мати обкладинку

**Код готовий. Всі перевірки пройдені. Проблема була в fallback логіці і compat properties.**
