// static/market/js/feed_following.js
// Feed from followed authors

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
      const res = await fetch(`/api/feed/following?page=${page}&per_page=${perPage}`);
      const data = await res.json();

      if (!data.ok) {
        if (data.error === "unauthorized") {
          window.location.href = "/login";
          return;
        }
        throw new Error(data.error || "Failed to load feed");
      }

      hideLoading();

      if (!data.items || data.items.length === 0) {
        showEmpty();
        return;
      }

      renderItems(data.items);
      renderPagination(data.page, data.pages);

    } catch (err) {
      console.error("Feed error:", err);
      hideLoading();
      grid.innerHTML = `<div class="error-message">Failed to load feed. Please try again.</div>`;
    }
  }

  function renderItems(items) {
    grid.innerHTML = items.map(renderCard).join("");
    emptyState.style.display = "none";
  }

  function renderCard(item) {
    const href = `/item/${item.id}`;
    const cover = item.cover_url || "/static/img/placeholder_stl.jpg";
    const title = escapeHtml(item.title || "Untitled");
    
    const isFree = item.is_free || !item.price_cents;
    const price = isFree ? "Free" : `${(item.price_cents / 100).toFixed(2)} zł`;
    
    const rating = item.rating ? item.rating.toFixed(1) : "0.0";
    const downloads = item.downloads || 0;

    return `
      <a class="feed-card" href="${href}">
        <div class="card-thumb">
          <img src="${cover}" loading="lazy" alt="${title}">
        </div>
        <div class="card-body">
          <h3 class="card-title">${title}</h3>
          <div class="card-stats">
            <span class="price">${price}</span>
            <span class="rating">⭐ ${rating}</span>
          </div>
          <div class="card-meta">
            <span>⬇ ${downloads}</span>
          </div>
        </div>
      </a>
    `;
  }

  function renderPagination(page, totalPages) {
    if (totalPages <= 1) {
      paginationWrap.innerHTML = "";
      return;
    }

    let html = '<div class="pagination">';

    if (page > 1) {
      html += `<button class="pg-btn" data-page="${page - 1}">‹ Prev</button>`;
    }

    const start = Math.max(1, page - 2);
    const end = Math.min(totalPages, page + 2);

    for (let p = start; p <= end; p++) {
      if (p === page) {
        html += `<span class="pg-btn active">${p}</span>`;
      } else {
        html += `<button class="pg-btn" data-page="${p}">${p}</button>`;
      }
    }

    if (page < totalPages) {
      html += `<button class="pg-btn" data-page="${page + 1}">Next ›</button>`;
    }

    html += '</div>';
    paginationWrap.innerHTML = html;

    // Bind pagination clicks
    paginationWrap.querySelectorAll("[data-page]").forEach(btn => {
      btn.addEventListener("click", () => {
        const p = parseInt(btn.dataset.page, 10);
        if (p && p !== currentPage) {
          currentPage = p;
          loadFeed(currentPage);
          window.scrollTo({ top: 0, behavior: "smooth" });
        }
      });
    });
  }

  function showLoading() {
    loadingState.style.display = "block";
    grid.innerHTML = "";
    emptyState.style.display = "none";
    paginationWrap.innerHTML = "";
  }

  function hideLoading() {
    loadingState.style.display = "none";
  }

  function showEmpty() {
    emptyState.style.display = "block";
    grid.innerHTML = "";
    paginationWrap.innerHTML = "";
  }

  function escapeHtml(str) {
    const div = document.createElement("div");
    div.textContent = str;
    return div.innerHTML;
  }
})();
