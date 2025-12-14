// static/market/js/top_prints.js
// Top Prints Leaderboard page

const state = {
  range: "all", // all | 7d | 30d
  page: 1,
  per_page: 24,
};

let currentUserFollows = null; // Track which authors user follows (null = not yet loaded)

// ========== DOM Elements ==========
const authorsList = document.getElementById("topAuthorsList");
const modelsList = document.getElementById("topModelsList");
const pagination = document.getElementById("topPrintsPagination");
const rangeBtns = document.querySelectorAll(".range-btn");

// ========== Fetch Data ==========
async function fetchTopPrints() {
  const params = new URLSearchParams({
    range: state.range,
    page: state.page,
    per_page: state.per_page,
  });

  const resp = await fetch(`/api/top-prints?${params}`);
  if (!resp.ok) throw new Error(`API error: ${resp.status}`);
  return await resp.json();
}

async function fetchUserFollows() {
  try {
    const resp = await fetch("/api/user/follows");
    if (!resp.ok) {
      currentUserFollows = new Set(); // Initialize empty on error
      return;
    }
    const data = await resp.json();
    if (data.ok && Array.isArray(data.follows)) {
      currentUserFollows = new Set(data.follows.map(f => f.followed_id));
    } else {
      currentUserFollows = new Set();
    }
    
    // Update all follow buttons after loading
    updateFollowButtons();
  } catch (err) {
    console.warn("Failed to fetch follows:", err);
    currentUserFollows = new Set();
  }
}

// ========== Follow/Unfollow ==========
async function toggleFollow(authorId) {
  try {
    const isFollowing = currentUserFollows.has(authorId);
    const method = isFollowing ? "DELETE" : "POST";
    const resp = await fetch(`/api/follow/${authorId}`, { method });
    
    if (resp.status === 401) {
      window.location.href = "/auth/login?next=" + encodeURIComponent(window.location.pathname);
      return;
    }
    
    if (!resp.ok) throw new Error(`Follow API error: ${resp.status}`);
    
    const data = await resp.json();
    if (data.ok) {
      if (data.following) {
        currentUserFollows.add(authorId);
      } else {
        currentUserFollows.delete(authorId);
      }
      return data.following;
    }
  } catch (err) {
    console.error("Follow error:", err);
    alert("Failed to update follow status");
  }
}

// ========== Render Functions ==========
function renderAuthorCard(author) {
  // If follows not yet loaded, show disabled button
  if (currentUserFollows === null) {
    return `
      <div class="author-card">
        <img src="${author.avatar_url}" alt="${author.name}" class="author-avatar">
        <div class="author-info">
          <h3 class="author-name">${escapeHtml(author.name)}</h3>
          <div class="author-stats">
            <span>🖨️ ${author.total_prints} prints</span>
            <span>📦 ${author.items_count} models</span>
          </div>
        </div>
        <button class="btn-follow" data-author-id="${author.id}" disabled>…</button>
      </div>
    `;
  }
  
  const isFollowing = currentUserFollows.has(author.id);
  
  return `
    <div class="author-card">
      <img src="${author.avatar_url}" alt="${author.name}" class="author-avatar">
      <div class="author-info">
        <h3 class="author-name">${escapeHtml(author.name)}</h3>
        <div class="author-stats">
          <span>🖨️ ${author.total_prints} prints</span>
          <span>📦 ${author.items_count} models</span>
        </div>
      </div>
      <button 
        class="btn-follow ${isFollowing ? 'is-following' : ''}" 
        data-author-id="${author.id}"
      >
        ${isFollowing ? '✓ Following' : '+ Follow'}
      </button>
    </div>
  `;
}

function renderModelCard(item) {
  const href = `/item/${item.slug || item.id}`;
  const cover = item.cover_url || "/static/img/placeholder_stl.jpg";
  const isFree = item.is_free || item.price === 0;
  const price = isFree ? "Free" : `${(item.price || 0).toFixed(2)} zł`;
  
  return `
    <a class="market-item-card tp-model-card" href="${href}">
      <div class="thumb">
        <img src="${cover}" loading="lazy" alt="${escapeHtml(item.title)}">
        <div class="prints-badge">🖨️ ${item.prints_count}</div>
      </div>
      <div class="meta">
        <div class="title">${escapeHtml(item.title)}</div>
        <div class="author-line">
          <img src="${item.author_avatar || '/static/img/user.jpg'}" class="author-mini-avatar">
          <span class="author-mini-name">${escapeHtml(item.author_name || 'Unknown')}</span>
        </div>
        <div class="row">
          <span class="price">${price}</span>
          <span class="rating">⭐ ${item.rating.toFixed(1)}</span>
        </div>
      </div>
    </a>
  `;
}

function renderPagination(page, pages) {
  if (pages <= 1) return "";
  
  let html = '<div class="pagination-inner">';
  
  if (page > 1) {
    html += `<button class="pg-btn" data-page="${page - 1}">‹</button>`;
  }
  
  const start = Math.max(1, page - 2);
  const end = Math.min(pages, page + 2);
  
  for (let p = start; p <= end; p++) {
    if (p === page) {
      html += `<span class="pg-btn is-active">${p}</span>`;
    } else {
      html += `<button class="pg-btn" data-page="${p}">${p}</button>`;
    }
  }
  
  if (page < pages) {
    html += `<button class="pg-btn" data-page="${page + 1}">›</button>`;
  }
  
  html += '</div>';
  return html;
}

function escapeHtml(str) {
  return String(str || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

// ========== Load & Display ==========
async function loadPage() {
  try {
    authorsList.innerHTML = '<div class="tp-loading">Loading authors...</div>';
    modelsList.innerHTML = '<div class="tp-loading">Loading models...</div>';
    pagination.innerHTML = "";
    
    const data = await fetchTopPrints();
    
    if (!data.ok) {
      throw new Error(data.error || "API error");
    }
    
    // Render authors
    if (data.top_authors && data.top_authors.length > 0) {
      authorsList.innerHTML = data.top_authors.map(renderAuthorCard).join("");
      bindFollowButtons();
    } else {
      authorsList.innerHTML = '<div class="tp-empty">No authors found for this period</div>';
    }
    
    // Render models
    if (data.items && data.items.length > 0) {
      modelsList.innerHTML = data.items.map(renderModelCard).join("");
    } else {
      modelsList.innerHTML = '<div class="tp-empty">No models found for this period</div>';
    }
    
    // Render pagination
    if (data.pages > 1) {
      pagination.innerHTML = renderPagination(data.page, data.pages);
      bindPagination();
    }
    
  } catch (err) {
    console.error("Load error:", err);
    authorsList.innerHTML = '<div class="tp-error">Failed to load data</div>';
    modelsList.innerHTML = '<div class="tp-error">Failed to load data</div>';
  }
}

// ========== Event Bindings ==========
function bindFollowButtons() {
  document.querySelectorAll(".btn-follow").forEach(btn => {
    btn.addEventListener("click", async (e) => {
      e.preventDefault();
      const authorId = parseInt(btn.dataset.authorId);
      btn.disabled = true;
      
      const isFollowing = await toggleFollow(authorId);
      
      if (isFollowing !== undefined) {
        btn.classList.toggle("is-following", isFollowing);
        btn.textContent = isFollowing ? "✓ Following" : "+ Follow";
      }
      
      btn.disabled = false;
    });
  });
}

function updateFollowButtons() {
  document.querySelectorAll(".btn-follow").forEach(btn => {
    const authorId = parseInt(btn.dataset.authorId);
    const isFollowing = currentUserFollows && currentUserFollows.has(authorId);
    
    btn.disabled = false;
    btn.classList.toggle("is-following", isFollowing);
    btn.textContent = isFollowing ? "✓ Following" : "+ Follow";
  });
}

function bindPagination() {
  pagination.querySelectorAll("[data-page]").forEach(btn => {
    btn.addEventListener("click", (e) => {
      e.preventDefault();
      const p = parseInt(btn.dataset.page);
      if (p !== state.page) {
        state.page = p;
        loadPage();
        window.scrollTo({ top: 0, behavior: "smooth" });
      }
    });
  });
}

// Range selector
rangeBtns.forEach(btn => {
  btn.addEventListener("click", () => {
    rangeBtns.forEach(b => b.classList.remove("active"));
    btn.classList.add("active");
    state.range = btn.dataset.range;
    state.page = 1;
    loadPage();
  });
});

// ========== Init ==========
(async () => {
  // Load page first (buttons will be disabled)
  const pageLoad = loadPage();
  
  // Load follows in parallel
  await fetchUserFollows();
  
  // Wait for page to finish rendering
  await pageLoad;
})();
