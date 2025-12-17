// static/market/js/feed_activity.js
// Unified activity feed from followed authors

(function() {
  const grid = document.getElementById("feedGrid");
  const emptyState = document.getElementById("emptyState");
  const loadingState = document.getElementById("loadingState");
  const paginationWrap = document.getElementById("paginationWrap");

  if (!grid) return;

  let currentPage = 1;
  const perPage = 24;

  // Initialize
  loadFeed(currentPage);

  async function loadFeed(page) {
    showLoading();

    try {
      const res = await fetch(`/api/feed/activity?page=${page}&per_page=${perPage}`, { credentials: "include" });
      const data = await res.json();

      if (!data.ok) {
        if (data.error === "unauthorized") {
          window.location.href = "/auth/login?next=" + encodeURIComponent(window.location.pathname);
          return;
        }
        throw new Error(data.error || "Failed to load feed");
      }

      hideLoading();

      if (!data.events || data.events.length === 0) {
        showEmpty();
        return;
      }

      renderEvents(data.events);
      renderPagination(data.page, data.pages);

    } catch (err) {
      console.error("Feed error:", err);
      hideLoading();
      grid.innerHTML = `<div class="error-message">Failed to load feed. Please try again.</div>`;
    }
  }

  function renderEvents(events) {
    grid.style.display = "block";
    emptyState.style.display = "none";
    
    grid.innerHTML = events.map(event => {
      switch(event.type) {
        case "new_item":
          return renderNewItem(event);
        case "new_make":
          return renderNewMake(event);
        case "new_review":
          return renderNewReview(event);
        default:
          return "";
      }
    }).join("");
  }

  function renderNewItem(event) {
    const time = formatTime(event.created_at);
    const item = event.item;
    const author = event.author;
    
    return `
      <a class="activity-card" href="${item.url}">
        <div class="activity-badge new-item">📦 New Model</div>
        <img src="${item.cover_url}" alt="${escapeHtml(item.title)}" class="activity-thumb" loading="lazy">
        <div class="activity-content">
          <div class="activity-author">
            <img src="${author.avatar_url}" class="author-avatar-mini">
            <strong>${escapeHtml(author.username)}</strong> published
          </div>
          <div class="activity-title">${escapeHtml(item.title)}</div>
          <div class="activity-time">${time}</div>
        </div>
      </a>
    `;
  }

  function renderNewMake(event) {
    const time = formatTime(event.created_at);
    const item = event.item;
    const author = event.author;
    const make = event.make;
    
    return `
      <a class="activity-card" href="${item.url}#makes">
        <div class="activity-badge new-make">🖨️ Print</div>
        <img src="${make.image_url || item.cover_url}" alt="Print" class="activity-thumb" loading="lazy">
        <div class="activity-content">
          <div class="activity-author">
            <img src="${author.avatar_url}" class="author-avatar-mini">
            <strong>${escapeHtml(make.user.username)}</strong> printed
          </div>
          <div class="activity-title">${escapeHtml(item.title)}</div>
          ${make.caption ? `<div class="activity-caption">"${escapeHtml(make.caption)}"</div>` : ''}
          <div class="activity-meta">
            <span>by ${escapeHtml(author.username)}</span>
            <span class="activity-time">${time}</span>
          </div>
        </div>
      </a>
    `;
  }

  function renderNewReview(event) {
    const time = formatTime(event.created_at);
    const item = event.item;
    const author = event.author;
    const review = event.review;
    const stars = '⭐'.repeat(review.rating);
    const verified = review.verified ? '<span class="verified-badge">✓ Verified</span>' : '';
    
    return `
      <a class="activity-card" href="${item.url}#reviews">
        <div class="activity-badge new-review">⭐ Review</div>
        <img src="${review.photo_url || item.cover_url}" alt="Review" class="activity-thumb" loading="lazy">
        <div class="activity-content">
          <div class="activity-author">
            <img src="${author.avatar_url}" class="author-avatar-mini">
            <strong>${escapeHtml(review.user.username)}</strong> reviewed
          </div>
          <div class="activity-title">${escapeHtml(item.title)}</div>
          <div class="activity-rating">${stars} ${verified}</div>
          ${review.text ? `<div class="activity-caption">"${escapeHtml(review.text.slice(0, 100))}${review.text.length > 100 ? '...' : ''}"</div>` : ''}
          <div class="activity-meta">
            <span>by ${escapeHtml(author.username)}</span>
            <span class="activity-time">${time}</span>
          </div>
        </div>
      </a>
    `;
  }

  function renderPagination(page, pages) {
    if (pages <= 1) {
      paginationWrap.innerHTML = "";
      return;
    }

    let html = '<div class="pagination">';
    
    if (page > 1) {
      html += `<button class="pg-btn" data-page="${page - 1}">‹ Previous</button>`;
    }
    
    html += `<span class="pg-info">Page ${page} of ${pages}</span>`;
    
    if (page < pages) {
      html += `<button class="pg-btn" data-page="${page + 1}">Next ›</button>`;
    }
    
    html += '</div>';
    paginationWrap.innerHTML = html;

    // Bind pagination buttons
    paginationWrap.querySelectorAll("[data-page]").forEach(btn => {
      btn.addEventListener("click", () => {
        const p = parseInt(btn.dataset.page);
        if (p !== currentPage) {
          currentPage = p;
          loadFeed(currentPage);
          window.scrollTo({ top: 0, behavior: "smooth" });
        }
      });
    });
  }

  function formatTime(dateStr) {
    const date = new Date(dateStr);
    const now = new Date();
    const diffMs = now - date;
    const diffMins = Math.floor(diffMs / 60000);
    const diffHours = Math.floor(diffMs / 3600000);
    const diffDays = Math.floor(diffMs / 86400000);

    if (diffMins < 1) return "just now";
    if (diffMins < 60) return `${diffMins}m ago`;
    if (diffHours < 24) return `${diffHours}h ago`;
    if (diffDays < 7) return `${diffDays}d ago`;
    
    return date.toLocaleDateString();
  }

  function escapeHtml(str) {
    return String(str || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function showLoading() {
    loadingState.style.display = "block";
    grid.style.display = "none";
    emptyState.style.display = "none";
    paginationWrap.innerHTML = "";
  }

  function hideLoading() {
    loadingState.style.display = "none";
  }

  function showEmpty() {
    grid.style.display = "none";
    emptyState.style.display = "block";
    paginationWrap.innerHTML = "";
  }
})();
