# Railway Debugging Instructions

## ✅ HOTFIX Applied

**Status:** Market endpoint now has robust fallback for missing `is_published` column

### What Changed:

1. **Added helper function** `_is_missing_column_error()` to detect SQL errors about missing columns
2. **Improved migration** `_ensure_publishing_columns()` with better error handling and logging
3. **Added fallback queries** in `/api/items` and `/api/my/items` that work without `is_published` columns
4. **Multi-level fallback chain:**
   - Try with `is_published` + `published_at`
   - If columns missing → retry without them
   - If that fails → legacy schema fallback

### Expected Behavior After Deploy:

✅ `/api/items` **never returns 500** even if columns don't exist
✅ `/market` page works immediately after deploy
✅ After migration runs → filter automatically starts working
✅ Logs will show `✅ Publishing columns added successfully` or warning

---

## Get Railway Logs (to debug if still failing)

### Option 1: Railway CLI (recommended)

```powershell
# Install Railway CLI if not installed
npm install -g @railway/cli

# Login
railway login

# Get recent logs
railway logs

# Get last 100 lines
railway logs --tail 100

# Follow logs in realtime
railway logs --follow
```

### Option 2: Railway Dashboard

1. Go to https://railway.app
2. Open your project
3. Click on your service (e.g., "web")
4. Click **"Deployments"** tab
5. Click on the latest deployment
6. Scroll to **"Logs"** section
7. Look for errors containing:
   - `/api/items`
   - `is_published`
   - `no such column`
   - `ProgrammingError`
   - `OperationalError`

### What to Look For:

```
ERROR: column "is_published" does not exist
LINE 1: SELECT id, title, price, tags, ... is_published, published_at
                                           ^
```

Or:

```
sqlalchemy.exc.ProgrammingError: (psycopg2.errors.UndefinedColumn) column "is_published" does not exist
```

### Send Me the Full Stacktrace:

Copy the **entire error block** including:
- Request path (e.g., `GET /api/items?page=1`)
- SQL query that failed
- Error type (ProgrammingError, OperationalError)
- Line numbers from traceback

---

## Manual Migration (if auto-migration fails)

If logs show migration isn't running, manually add columns via Railway:

```sql
-- PostgreSQL
ALTER TABLE items ADD COLUMN IF NOT EXISTS is_published BOOLEAN DEFAULT TRUE;
ALTER TABLE items ADD COLUMN IF NOT EXISTS published_at TIMESTAMP;

-- Or SQLite (if using)
ALTER TABLE items ADD COLUMN is_published INTEGER DEFAULT 1;
ALTER TABLE items ADD COLUMN published_at TIMESTAMP;
```

### How to Run SQL on Railway:

1. Railway Dashboard → your service
2. Click **"Data"** tab
3. Open database service
4. Click **"Query"** or use connection string with `psql`

---

## Test After Deploy

```bash
# Test public market (should work even without columns)
curl https://your-app.railway.app/api/items?page=1

# Test my items (should work even without columns)
curl https://your-app.railway.app/api/my/items \
  -H "Cookie: session=YOUR_SESSION"

# Both should return 200 OK with items array
```

---

## Migration Check

After deploy, check logs for these messages:

✅ **Success:**
```
✅ Publishing columns added successfully
```

⚠️ **Already exists (OK):**
```
⚠️ Migration failed (columns may already exist): column "is_published" already exists
```

❌ **Error (needs investigation):**
```
❌ Migration error (continuing anyway): [detailed error]
```

---

## Current Code Status

### Files Modified:
- ✅ `market.py` - HOTFIX applied
- ✅ `models.py` - fields added
- ✅ `my-ads.js` - UI updated
- ✅ `my-ads.css` - styles added

### Migration Strategy:
1. `@bp.before_app_request` runs on first market/API request
2. Checks if `is_published` column exists
3. If not → adds columns (PostgreSQL: IF NOT EXISTS, SQLite: try-catch)
4. Never crashes - always logs and continues

### Fallback Chain:
1. Try SELECT with `is_published, published_at` ✅
2. If missing column error → retry without these fields ✅
3. If that fails → legacy schema (file_url instead of stl_main_url) ✅
4. Result: **always returns data**, never 500

---

## Next Steps

1. **Deploy to Railway**
2. **Check logs** with `railway logs --tail 100`
3. **Test** `/api/items` and `/market` pages
4. **Report** if you still see 500 errors

If errors persist, send me:
- Full stacktrace from Railway logs
- Database type (PostgreSQL/MySQL/SQLite)
- Output of `SELECT column_name FROM information_schema.columns WHERE table_name='items'`
