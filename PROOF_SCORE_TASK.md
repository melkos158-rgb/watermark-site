# Proof Score (MVP) - Technical Specification

## 📋 Overview
Implement printability analysis for STL files in this Flask marketplace app. Compute a 0-100 score based on geometry quality, overhang detection, and manifold validation — all in pure Python, no external dependencies.

---

## 🗄️ Database Migration (Run First)

**File:** `migrate_proof_score.sql` (already created)

### PostgreSQL (Railway Production):
```sql
ALTER TABLE market_item ADD COLUMN IF NOT EXISTS printability_json TEXT;
ALTER TABLE market_item ADD COLUMN IF NOT EXISTS proof_score INTEGER;
ALTER TABLE market_item ADD COLUMN IF NOT EXISTS analyzed_at TIMESTAMP;
```

### SQLite (Local Development):
```sql
ALTER TABLE market_item ADD COLUMN printability_json TEXT;
ALTER TABLE market_item ADD COLUMN proof_score INTEGER;
ALTER TABLE market_item ADD COLUMN analyzed_at TEXT;
```

---

## 📁 Files to Modify

### 1. `models.py` (Line ~35-120, class MarketItem)
**Current state:** Has basic fields (id, title, price, cover_url, stl_main_url, gallery_urls, etc.)

**Add these 3 nullable fields:**
```python
# ---------- printability analysis ----------
printability_json = _db.Column(_db.Text, nullable=True)  # JSON string with metrics
proof_score = _db.Column(_db.Integer, nullable=True)    # 0-100 heuristic score
analyzed_at = _db.Column(_db.DateTime, nullable=True)   # timestamp of last analysis
```

**Add property to to_dict() method:**
```python
def to_dict(self) -> dict:
    return {
        # ... existing fields ...
        "proof_score": self.proof_score,
        "printability_json": self.printability_json,
        # ... rest ...
    }
```

---

### 2. `market.py` (Main Backend Logic)
**Current state:** Has api_items(), routes, upload helpers at top (lines 1-200+)

#### A) Add STL Analysis Function (place near top, after imports)

```python
def analyze_stl(stl_path: str) -> dict:
    """
    Pure Python STL analyzer (ASCII + Binary support).
    
    Returns:
    {
        "triangles": int,
        "bbox_mm": [x, y, z],
        "volume_mm3": float | null,
        "weight_g": float | null,
        "overhang_percent": float,
        "warnings": ["non_manifold", "degenerate_faces", ...],
        "proof_score": int (0-100)
    }
    """
    # Implementation notes:
    # 1. Detect ASCII vs Binary (first 5 bytes != "solid")
    # 2. Parse triangles, compute bbox, edge counts
    # 3. Overhang: faces with normal.z < -cos(45°)
    # 4. Manifold: edge appears exactly 2 times (not 1, not >2)
    # 5. Degenerate: triangle with area < 1e-6
    # 6. Volume: signed tetrahedra sum (can be unreliable for non-manifold)
    # 7. Weight: volume_mm3 / 1000 * 1.24 (PLA density)
    # 8. Proof score heuristic:
    #    - Start 100
    #    - -20 if non-manifold
    #    - -10 if degenerate faces
    #    - -1 per 10% overhang
    #    - min 0
    pass  # TODO: implement
```

**Key requirements:**
- Support ASCII STL (`solid ... endsolid`)
- Support Binary STL (80-byte header + 4-byte count + triangles)
- No dependencies (no numpy, trimesh, etc.) — pure Python + struct
- Return dict with all metrics + warnings list
- Compute proof_score 0-100 using heuristic penalties

#### B) Add API Endpoint (place with other /api/ routes)

```python
@bp.route('/api/item/<int:item_id>/printability', methods=['GET'])
def api_printability(item_id):
    """
    GET /api/item/123/printability
    
    Returns cached analysis from DB if present.
    Otherwise analyzes STL file, saves to DB, returns fresh data.
    
    Response:
    {
        "ok": true,
        "item_id": 123,
        "proof_score": 85,
        "printability": {
            "triangles": 1234,
            "bbox_mm": [50, 30, 20],
            "volume_mm3": 15000.5,
            "weight_g": 18.6,
            "overhang_percent": 5.2,
            "warnings": []
        },
        "analyzed_at": "2025-12-15T10:30:00Z"
    }
    
    Error cases:
    - Item not found: {"ok": false, "error": "item_not_found"}
    - No STL file: {"ok": false, "error": "no_stl_file"}
    - Analysis failed: {"ok": false, "error": "analysis_failed", "detail": "..."}
    """
    # 1. Fetch MarketItem by ID
    # 2. If printability_json exists and recent (< 1 hour old?), return from DB
    # 3. Else find STL file path (item.stl_main_url → convert to filesystem path)
    # 4. Call analyze_stl(path)
    # 5. Save results to item.printability_json (JSON string), item.proof_score, item.analyzed_at
    # 6. db.session.commit()
    # 7. Return JSON response with Cache-Control: no-store
    pass  # TODO: implement
```

#### C) Hook Analysis into Upload Flow

Find where STL files are saved after upload (likely in routes that handle POST with file upload).

**Add after successful STL save:**
```python
# After: item.stl_main_url = saved_url
# Before: db.session.commit()

# Trigger printability analysis
if item.stl_main_url:
    try:
        stl_path = _resolve_stl_filesystem_path(item.stl_main_url)
        if stl_path and os.path.isfile(stl_path):
            analysis = analyze_stl(stl_path)
            item.printability_json = json.dumps(analysis)
            item.proof_score = analysis.get("proof_score")
            item.analyzed_at = datetime.utcnow()
    except Exception as e:
        current_app.logger.warning(f"STL analysis failed for item {item.id}: {e}")
        # Don't block upload — just log and continue
```

**Helper function to convert URL → filesystem path:**
```python
def _resolve_stl_filesystem_path(url: str) -> Optional[str]:
    """
    Convert /media/... or /static/market_uploads/... URL to absolute filesystem path.
    Returns None if file doesn't exist or URL is external (Cloudinary).
    """
    # Handle Cloudinary URLs
    if url.startswith("http://") or url.startswith("https://"):
        return None  # External URL, can't analyze locally
    
    # Handle /media/... → uploads_root
    if url.startswith("/media/"):
        rel = url[len("/media/"):].lstrip("/")
        path = os.path.join(_uploads_root(), rel)
        return path if os.path.isfile(path) else None
    
    # Handle /static/market_uploads/... → legacy static
    if url.startswith("/static/market_uploads/"):
        rel = url[len("/static/market_uploads/"):].lstrip("/")
        path = os.path.join(current_app.root_path, "static", "market_uploads", rel)
        return path if os.path.isfile(path) else None
    
    return None
```

---

### 3. `templates/market/detail.html` (Item Detail Page)
**Current state:** Lines 1-50 show header with title, rating, downloads, price, author

**Add Proof Score Panel (place after meta section, before description):**

```html
<!-- Proof Score Panel (loaded async) -->
<section class="proof-score-panel" id="proofScorePanel" style="display:none;">
  <h3>🔍 Printability Analysis</h3>
  <div class="proof-score-badge">
    <span class="score" id="proofScoreValue">—</span>
    <span class="label">/100</span>
  </div>
  <div class="metrics" id="proofMetrics">
    <p>Loading analysis...</p>
  </div>
  <div class="warnings" id="proofWarnings"></div>
</section>

<script>
// Fetch proof score on page load
(async function loadProofScore() {
  const itemId = {{ item.id }};
  try {
    const res = await fetch(`/api/item/${itemId}/printability`);
    const data = await res.json();
    
    if (!data.ok) {
      console.warn('Proof score unavailable:', data.error);
      return;
    }
    
    // Show panel
    document.getElementById('proofScorePanel').style.display = 'block';
    
    // Update score badge
    const scoreEl = document.getElementById('proofScoreValue');
    scoreEl.textContent = data.proof_score || '—';
    scoreEl.className = 'score ' + getScoreClass(data.proof_score);
    
    // Update metrics
    const p = data.printability || {};
    const metricsHTML = `
      <p><strong>Triangles:</strong> ${p.triangles || '—'}</p>
      <p><strong>Bounding Box:</strong> ${formatBbox(p.bbox_mm)}</p>
      <p><strong>Volume:</strong> ${formatVolume(p.volume_mm3)}</p>
      <p><strong>Est. Weight (PLA):</strong> ${formatWeight(p.weight_g)}</p>
      <p><strong>Overhang:</strong> ${p.overhang_percent ? p.overhang_percent.toFixed(1) + '%' : '—'}</p>
    `;
    document.getElementById('proofMetrics').innerHTML = metricsHTML;
    
    // Update warnings
    if (p.warnings && p.warnings.length > 0) {
      const warningsHTML = '<h4>⚠️ Warnings:</h4><ul>' +
        p.warnings.map(w => `<li>${formatWarning(w)}</li>`).join('') +
        '</ul>';
      document.getElementById('proofWarnings').innerHTML = warningsHTML;
    }
    
  } catch (err) {
    console.error('Failed to load proof score:', err);
  }
})();

function getScoreClass(score) {
  if (score >= 80) return 'excellent';
  if (score >= 60) return 'good';
  if (score >= 40) return 'fair';
  return 'poor';
}

function formatBbox(bbox) {
  if (!bbox || bbox.length !== 3) return '—';
  return `${bbox[0].toFixed(1)} × ${bbox[1].toFixed(1)} × ${bbox[2].toFixed(1)} mm`;
}

function formatVolume(vol) {
  if (!vol) return '—';
  return `${(vol / 1000).toFixed(2)} cm³`;
}

function formatWeight(w) {
  if (!w) return '—';
  return `${w.toFixed(1)} g`;
}

function formatWarning(w) {
  const labels = {
    'non_manifold': 'Non-manifold geometry (edges not paired)',
    'degenerate_faces': 'Degenerate triangles detected',
    'volume_unreliable': 'Volume calculation may be inaccurate'
  };
  return labels[w] || w;
}
</script>

<style>
.proof-score-panel {
  background: #f5f5f5;
  border: 1px solid #ddd;
  border-radius: 8px;
  padding: 1rem;
  margin: 1rem 0;
}

.proof-score-badge {
  font-size: 2rem;
  font-weight: bold;
  text-align: center;
  margin: 0.5rem 0;
}

.proof-score-badge .score.excellent { color: #28a745; }
.proof-score-badge .score.good { color: #17a2b8; }
.proof-score-badge .score.fair { color: #ffc107; }
.proof-score-badge .score.poor { color: #dc3545; }

.proof-score-panel .metrics p {
  margin: 0.25rem 0;
  font-size: 0.9rem;
}

.proof-score-panel .warnings {
  margin-top: 0.5rem;
  color: #856404;
  background: #fff3cd;
  border: 1px solid #ffeeba;
  border-radius: 4px;
  padding: 0.5rem;
}
</style>
```

---

### 4. `templates/market/_item_card.html` (Grid Card)
**Current state:** Lines 1-80 show card with badges (FREE, BESTSELLER, TRENDING, NEW)

**Add Proof Score Badge (place after existing badges, before thumb closing tag):**

```html
<!-- Existing badges -->
{% if it.is_free %}
  <span class="badge free">FREE</span>
{% elif it.downloads and it.downloads > 200 %}
  <span class="badge best">BESTSELLER</span>
{% elif it.trending %}
  <span class="badge trend">TRENDING</span>
{% elif it.created_at and it.created_at >= (now - timedelta(days=7)) %}
  <span class="badge new">NEW</span>
{% endif %}

<!-- NEW: Proof Score Badge -->
{% if it.proof_score is not none %}
  {% if it.proof_score >= 80 %}
    <span class="badge proof excellent" title="Printability Score: {{ it.proof_score }}/100">
      🖨️ {{ it.proof_score }}
    </span>
  {% elif it.proof_score >= 60 %}
    <span class="badge proof good" title="Printability Score: {{ it.proof_score }}/100">
      🖨️ {{ it.proof_score }}
    </span>
  {% else %}
    <span class="badge proof fair" title="Printability Score: {{ it.proof_score }}/100">
      PS: {{ it.proof_score }}
    </span>
  {% endif %}
{% endif %}
```

**Add CSS for proof badge (in static/css/market_cards.css or inline):**

```css
.badge.proof {
  background: #17a2b8;
  color: white;
  font-size: 0.8rem;
  padding: 2px 6px;
  position: absolute;
  top: 8px;
  right: 8px;
  border-radius: 3px;
  font-weight: bold;
}

.badge.proof.excellent {
  background: #28a745;
}

.badge.proof.good {
  background: #17a2b8;
}

.badge.proof.fair {
  background: #ffc107;
  color: #333;
}
```

---

## 🧪 Implementation Checklist

- [ ] Run SQL migration on Railway (PostgreSQL)
- [ ] Run SQL migration locally (SQLite)
- [ ] Add 3 fields to MarketItem model in models.py
- [ ] Implement analyze_stl() function in market.py (pure Python)
- [ ] Add GET /api/item/<id>/printability endpoint
- [ ] Add _resolve_stl_filesystem_path() helper
- [ ] Hook analysis into upload flow (after STL save)
- [ ] Add Proof Score panel to templates/market/detail.html
- [ ] Add Proof Score badge to templates/market/_item_card.html
- [ ] Test with sample STL file (upload → check analysis → view detail page)
- [ ] Verify no external dependencies added (keep pure Python)

---

## 🎯 Success Criteria

1. **Upload:** New STL uploads automatically get analyzed
2. **API:** GET /api/item/123/printability returns cached or fresh analysis
3. **Detail Page:** Shows proof score badge + metrics + warnings
4. **Grid Cards:** Shows small proof score badge (🖨️ 85 or PS: 45)
5. **No Dependencies:** Works without trimesh, numpy, etc.
6. **Graceful Degradation:** If analysis fails, don't block upload

---

## 📚 Reference

**STL Format:**
- Binary: 80-byte header + uint32 triangle count + (12 floats + 2-byte attr) per triangle
- ASCII: `solid name ... facet normal ... outer loop ... vertex ... endloop ... endfacet ... endsolid`

**Manifold Check:**
- Each edge (pair of vertices) must appear exactly 2 times
- Build edge → count map, flag if any count != 2

**Overhang Detection:**
- Normal vector (nx, ny, nz) points outward
- If nz < -cos(45°) ≈ -0.707, face is overhang (printing without support)

**Volume Calculation:**
- Signed tetrahedra: V = Σ (v0 · (v1 × v2)) / 6
- Only reliable for manifold meshes

**Proof Score Heuristic:**
```python
score = 100
if non_manifold: score -= 20
if degenerate_count > 0: score -= 10
score -= int(overhang_percent / 10)  # -1 per 10%
return max(0, score)
```

---

## 🚀 Deployment Notes

- Railway auto-migrates on push (add ALTER TABLE to init script or run manually)
- Local SQLite: run migration via `sqlite3 market.db < migrate_proof_score.sql`
- No new packages in requirements.txt (pure Python implementation)
- Cache analysis results in DB to avoid re-processing on every page load
- Add Cache-Control: no-store to API endpoint (like follow endpoints)

---

**Ready to implement! 🎉**
