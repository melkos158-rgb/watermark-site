# 🚀 Deployment Checklist - Cloudinary + Chunked Upload

## ✅ Pre-Deployment Verification

- [x] Python syntax check passed (`python -m py_compile market_api.py`)
- [x] JavaScript syntax check passed (no errors in upload_manager.js)
- [x] All imports verified (`os`, `json`, `Path`, `re`, `send_from_directory`)
- [x] Documentation created (CLOUDINARY_CHUNKED_UPLOAD.md)

## 📋 Railway Deployment Steps

### Step 1: Set Environment Variables

Go to Railway Dashboard → Your Project → Settings → Variables

```bash
# Required for Cloudinary video/image uploads
CLOUDINARY_CLOUD_NAME=your-cloud-name

# Optional: for unsigned uploads (recommended)
CLOUDINARY_UNSIGNED_PRESET=proofly_unsigned

# Alternative: Use CLOUDINARY_URL (will auto-parse cloud_name)
CLOUDINARY_URL=cloudinary://api_key:api_secret@cloud_name

# Upload directory (Railway volume)
UPLOAD_FOLDER=/uploads
```

### Step 2: Create Cloudinary Unsigned Preset

1. Go to Cloudinary Dashboard: https://console.cloudinary.com/
2. Navigate to: **Settings → Upload → Upload presets**
3. Click **Add upload preset**
4. Settings:
   - **Preset name:** `proofly_unsigned`
   - **Signing Mode:** **Unsigned** ⚠️ IMPORTANT
   - **Folder:** Leave empty (set by frontend)
   - **Use filename:** Yes
   - **Unique filename:** Yes (recommended)
5. Click **Save**

### Step 3: Deploy Code

```bash
# Commit changes
git add market_api.py static/market/js/upload_manager.js
git commit -m "feat: Cloudinary unsigned upload + chunked upload for large files

- Safe Cloudinary detection from ENV (CLOUDINARY_CLOUD_NAME or CLOUDINARY_URL)
- Return cloudinary config with unsigned_preset in draft creation
- Frontend injects upload_preset + folder for Cloudinary uploads
- Chunked upload for ZIP/STL files (8MB chunks) to prevent Railway timeout
- New media serving endpoint /api/market/media/<item_id>/<filename>
- Accurate progress tracking based on uploaded bytes"

# Push to Railway (triggers auto-deploy)
git push origin main
```

### Step 4: Monitor Deployment

```bash
# Watch Railway logs
railway logs --follow

# Look for:
# ✅ "[DRAFT] Cloudinary enabled: cloud=xxx preset=yyy"
# ✅ No errors during startup
```

## 🧪 Post-Deployment Testing

### Test 1: Draft Creation with Cloudinary Config

```bash
# Create draft item
curl -X POST https://yourapp.railway.app/api/market/items/draft \
  -H "Content-Type: application/json" \
  -H "Cookie: session=YOUR_SESSION_COOKIE" \
  -d '{"title":"Test Upload","price":0,"tags":"test","desc":"Testing upload system"}'
```

**Expected Response:**
```json
{
  "ok": true,
  "item_id": 123,
  "upload_urls": {
    "video": "https://api.cloudinary.com/v1_1/your-cloud-name/video/upload",
    "cover": "https://api.cloudinary.com/v1_1/your-cloud-name/image/upload",
    "stl": "https://yourapp.railway.app/api/market/items/123/upload/stl",
    "zip": "https://yourapp.railway.app/api/market/items/123/upload/zip"
  },
  "cloudinary": {
    "cloud_name": "your-cloud-name",
    "unsigned_preset": "proofly_unsigned"
  }
}
```

**Troubleshooting:**
- ❌ `cloudinary: null` → Check ENV variables are set correctly
- ❌ `unauthorized` → Login first and use valid session cookie

---

### Test 2: Small File Upload (Simple Mode)

1. Go to: https://yourapp.railway.app/market/upload
2. Upload small image (< 8MB)
3. Check browser console:
   ```
   [UPLOAD] Draft created: 123
   [UPLOAD] cover uploaded: https://res.cloudinary.com/...
   ```
4. Verify in Cloudinary Dashboard:
   - Path: `proofly/items/123/cover.jpg`
   - Upload preset: `proofly_unsigned`

---

### Test 3: Large File Upload (Chunked Mode)

1. Upload large STL file (> 50MB)
2. Check browser console:
   ```
   [CHUNK] Starting chunked upload: file=model.stl size=52428800 chunks=7
   [CHUNK] Uploaded 1/7 (14%)
   [CHUNK] Uploaded 2/7 (28%)
   ...
   [CHUNK] ✅ Upload complete: https://yourapp.railway.app/api/market/media/123/stl_model.stl
   ```
3. Verify file is accessible:
   ```bash
   curl -I https://yourapp.railway.app/api/market/media/123/stl_model.stl
   # Should return: HTTP/1.1 200 OK
   ```

---

### Test 4: Progress Bar

1. Start large file upload
2. Immediately navigate to different page (e.g., /market)
3. **Expected:** Progress bar appears at top
4. **Expected:** Progress updates 0% → 100%
5. **Expected:** Toast notification: "Модель опублікована!"
6. Refresh page
7. **Expected:** Progress bar restores from localStorage

---

### Test 5: Cloudinary Preset Injection

Open browser DevTools → Network → Upload file → Find Cloudinary request

**Request Payload:**
```
------WebKitFormBoundary...
Content-Disposition: form-data; name="file"; filename="video.mp4"
Content-Type: video/mp4

[video data]
------WebKitFormBoundary...
Content-Disposition: form-data; name="upload_preset"

proofly_unsigned
------WebKitFormBoundary...
Content-Disposition: form-data; name="folder"

proofly/items/123
------WebKitFormBoundary...
```

**Troubleshooting:**
- ❌ Missing `upload_preset` → Check frontend receives `cloudinary` object
- ❌ 401 Unauthorized → Cloudinary preset not set to "Unsigned" mode

---

## 🐛 Common Issues & Fixes

### Issue 1: "Cloudinary not configured" in logs

**Symptoms:**
```
[DRAFT] Cloudinary not configured
cloudinary: null in API response
```

**Fix:**
```bash
# Check ENV variable is set
railway variables

# If missing, add:
railway variables set CLOUDINARY_CLOUD_NAME=your-cloud-name
railway variables set CLOUDINARY_UNSIGNED_PRESET=proofly_unsigned

# Restart app
railway restart
```

---

### Issue 2: "Upload failed: 401" from Cloudinary

**Symptoms:**
```
[UPLOAD] Upload failed: 401
Cloudinary returns: {"error": {"message": "Invalid upload preset"}}
```

**Fix:**
1. Go to Cloudinary Dashboard
2. Settings → Upload → Upload presets
3. Find `proofly_unsigned` preset
4. **Change Signing Mode to "Unsigned"** ⚠️
5. Save and retry upload

---

### Issue 3: "Chunk upload timeout"

**Symptoms:**
```
[CHUNK] Uploaded 1/10 (10%)
Network error during chunk upload
```

**Fix:**
- Check Railway volume has space: `railway volume ls`
- Verify `UPLOAD_FOLDER` ENV is set correctly
- Check Railway logs for errors

---

### Issue 4: "404 on media URL"

**Symptoms:**
```
GET /api/market/media/123/stl_model.stl → 404 Not Found
```

**Fix:**
1. Verify `serve_media()` endpoint exists in market_api.py
2. Check file was actually uploaded:
   ```bash
   railway run ls /uploads/market_items/123/
   ```
3. Verify blueprint is registered in app.py:
   ```python
   from market_api import bp as market_api_bp
   app.register_blueprint(market_api_bp, url_prefix='/api/market')
   ```

---

### Issue 5: "Progress bar not updating"

**Symptoms:**
- Progress bar stuck at 0%
- No updates in console

**Fix:**
1. Check XHR progress event listener:
   ```javascript
   xhr.upload.addEventListener('progress', (e) => {
     console.log('Progress:', e.loaded, '/', e.total);
   });
   ```
2. Verify `updateProgress()` is called
3. Check localStorage persistence:
   ```javascript
   localStorage.getItem('proofly_uploads')
   ```

---

## 📊 Monitoring

### Railway Logs to Watch

```bash
railway logs --follow | grep -E "DRAFT|CHUNK|UPLOAD"
```

**Good Signs:**
```
[DRAFT] Cloudinary enabled: cloud=your-cloud-name preset=proofly_unsigned
[DRAFT] Created item_id=123 for uid=456
[CHUNK] item=123 type=stl chunk=1/10 size=8388608 bytes
[CHUNK] ✅ Upload completed: item=123 type=stl url=...
[ATTACH] Item 123 published successfully
```

**Bad Signs:**
```
[DRAFT] Cloudinary not configured
[CHUNK] Error writing chunk: [Errno 28] No space left on device
[FAV] Database error: ... (unrelated to upload)
```

---

## 🎯 Success Metrics

After successful deployment, you should see:

- ✅ **Instant redirect:** Click "Publish" → /market in <1s
- ✅ **Background upload:** Progress bar appears at top
- ✅ **No timeouts:** Large files (200MB+) upload successfully
- ✅ **Cloudinary organized:** Files in `proofly/items/{id}/` folder
- ✅ **Accurate progress:** Bar updates smoothly 0% → 100%
- ✅ **Persistent state:** Progress survives page refresh
- ✅ **Video preview works:** Hover → autoplay (on item cards)

---

## 🔄 Rollback Plan

If deployment fails:

```bash
# Revert commit
git revert HEAD

# Or hard reset to previous commit
git reset --hard HEAD~1
git push origin main --force

# Railway will auto-deploy previous version
```

---

## 📞 Support

If issues persist after following this checklist:

1. Check Railway logs: `railway logs --tail 100`
2. Verify ENV variables: `railway variables`
3. Test API manually: `curl https://yourapp.railway.app/api/market/items/draft`
4. Check Cloudinary dashboard for upload attempts
5. Review browser console for frontend errors

---

**Status:** Ready for deployment ✅  
**Estimated deployment time:** 5-10 minutes  
**Expected downtime:** 0 seconds (rolling deployment)
