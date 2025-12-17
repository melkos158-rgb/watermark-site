// static/js/notifications.js
// Централізований менеджер нотифікацій для Proofly STL Market.
//
// Очікуваний бекенд (зробимо в notifications_api.py):
//   GET  /api/notifications?scope=unread|all
//        -> { ok:true, items:[...], unread_count: N }
//
//   POST /api/notifications/mark_all_read
//        -> { ok:true, unread_count: 0 }
//
//   POST /api/notifications/<id>/read
//        -> { ok:true, item:{...}, unread_count: N }
//
// Формат нотифікації (item):
//   {
//     id,
//     type: "system|order|comment|ai|printability|other",
//     level: "info|success|warning|error",
//     title,
//     body,
//     link,          // опційний URL
//     created_at,    // ISO string
//     read_at,       // ISO string or null
//   }
//
// HTML-хуки (на повній сторінці notifications.html):
//   #notif-list         – контейнер для списку
//   #notif-empty        – текст "нема нотифікацій"
//   #notif-status       – стрічка статусу/помилки
//   #notif-counter      – бейдж (наприклад у шапці)
//   #notif-filter       – select (all|unread)
//   #notif-mark-all     – кнопка "Позначити всі прочитаними"
//   #notif-refresh      – кнопка "Оновити"
//
// У навбарі можна підʼєднати тільки дзвіночок + бейдж:
//   initNotifications({ bellId:"nav-notif-bell", counterId:"nav-notif-count" });

export function initNotifications({
  listId = "notif-list",
  emptyId = "notif-empty",
  statusId = "notif-status",
  counterId = "notif-counter",
  filterId = "notif-filter",
  markAllId = "notif-mark-all",
  refreshId = "notif-refresh",
  bellId = "notif-bell",
  dropdownId = "notif-dropdown", // для дропдауна в навбарі (опційно)
  autoPoll = false,
  pollIntervalMs = 60_000, // 1 хв
} = {}) {
  const $ = (id) => (id ? document.getElementById(id) : null);

  const listEl = $(listId);
  const emptyEl = $(emptyId);
  const statusEl = $(statusId);
  const counterEl = $(counterId);
  const filterEl = $(filterId);
  const btnMarkAll = $(markAllId);
  const btnRefresh = $(refreshId);
  const bellEl = $(bellId);
  const dropdownEl = $(dropdownId);

  // СТАН
  let items = [];
  let unreadCount = 0;
  let scope = "all"; // "all" | "unread"
  let isLoading = false;
  let dropdownOpen = false;
  let pollTimer = null;

  // ===== УТИЛІТИ =====

  function setStatus(msg, kind = "info") {
    if (!statusEl) return;
    const color =
      kind === "error"
        ? "#f97373"
        : kind === "success"
        ? "#4ade80"
        : "#e5e7eb";
    statusEl.textContent = msg || "";
    statusEl.style.color = color;
  }

  function apiFetch(url, options = {}) {
    const opts = {
      headers: {
        "Content-Type": "application/json",
        ...(options.headers || {}),
      },
      credentials: "include",
      ...options,
    };
    return fetch(url, opts).then(async (res) => {
      let data;
      try {
        data = await res.json();
      } catch (e) {
        throw new Error("Invalid JSON from server");
      }
      if (!res.ok || data.ok === false) {
        const msg = (data && data.error) || `HTTP ${res.status}`;
        throw new Error(msg);
      }
      return data;
    });
  }

  function escapeHtml(str) {
    if (str == null) return "";
    return String(str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function timeAgo(iso) {
    if (!iso) return "";
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return "";
    const now = new Date();
    const diffMs = now.getTime() - d.getTime();
    const sec = Math.floor(diffMs / 1000);
    if (sec < 60) return "щойно";
    const min = Math.floor(sec / 60);
    if (min < 60) return `${min} хв тому`;
    const h = Math.floor(min / 60);
    if (h < 24) return `${h} год тому`;
    const days = Math.floor(h / 24);
    if (days < 7) return `${days} дн тому`;
    return d.toLocaleDateString();
  }

  function levelIcon(level) {
    switch (level) {
      case "success":
        return "✅";
      case "warning":
        return "⚠️";
      case "error":
        return "⛔";
      default:
        return "🔔";
    }
  }

  function typeLabel(type) {
    switch (type) {
      case "order":
        return "Замовлення";
      case "comment":
        return "Коментар";
      case "ai":
        return "AI";
      case "printability":
        return "Printability";
      case "system":
        return "Система";
      default:
        return "Подія";
    }
  }

  // ===== РЕНДЕР =====

  function updateCounter() {
    if (!counterEl) return;
    const n = unreadCount || 0;
    if (n <= 0) {
      counterEl.textContent = "";
      counterEl.style.display = "none";
    } else {
      counterEl.textContent = n > 99 ? "99+" : String(n);
      counterEl.style.display = "inline-flex";
    }
  }

  function renderList() {
    if (!listEl) return;

    listEl.innerHTML = "";
    if (!items.length) {
      if (emptyEl) emptyEl.style.display = "block";
      return;
    }
    if (emptyEl) emptyEl.style.display = "none";

    items.forEach((n) => {
      const wrapper = document.createElement("div");
      wrapper.className = "notif-item";
      wrapper.dataset.id = n.id;

      const isUnread = !n.read_at;
      const level = n.level || "info";
      const icon = levelIcon(level);
      const type = typeLabel(n.type);

      wrapper.innerHTML = `
        <div class="notif-item-main">
          <div class="notif-item-icon">${icon}</div>
          <div class="notif-item-body">
            <div class="notif-item-header">
              <span class="notif-item-title">
                ${escapeHtml(n.title || "(без заголовка)")}
              </span>
              ${
                isUnread
                  ? '<span class="notif-item-pill notif-item-pill-unread">Новe</span>'
                  : ""
              }
            </div>
            <div class="notif-item-text">
              ${escapeHtml(n.body || "")}
            </div>
            <div class="notif-item-meta">
              <span>${escapeHtml(type)}</span>
              <span>·</span>
              <span>${escapeHtml(timeAgo(n.created_at))}</span>
            </div>
          </div>
        </div>
        <div class="notif-item-actions">
          ${
            n.link
              ? '<button type="button" class="notif-btn notif-btn-link">Відкрити</button>'
              : ""
          }
          ${
            isUnread
              ? '<button type="button" class="notif-btn notif-btn-read">Прочитано</button>'
              : ""
          }
        </div>
      `;

      // клік по всій картці -> якщо є link, відкриваємо
      wrapper.addEventListener("click", (ev) => {
        const target = ev.target;
        const isButton =
          target &&
          target.classList &&
          (target.classList.contains("notif-btn-link") ||
            target.classList.contains("notif-btn-read"));
        // Локальні хендлери нижче
        if (isButton) return;

        if (n.link) {
          markRead(n.id, { silent: true }); // не чекаємо на відповідь
          window.location.href = n.link;
        } else if (isUnread) {
          markRead(n.id);
        }
      });

      // кнопка "Відкрити"
      const btnLink = wrapper.querySelector(".notif-btn-link");
      if (btnLink) {
        btnLink.addEventListener("click", (ev) => {
          ev.stopPropagation();
          if (n.link) {
            markRead(n.id, { silent: true });
            window.location.href = n.link;
          }
        });
      }

      // кнопка "Прочитано"
      const btnRead = wrapper.querySelector(".notif-btn-read");
      if (btnRead) {
        btnRead.addEventListener("click", (ev) => {
          ev.stopPropagation();
          markRead(n.id);
        });
      }

      if (isUnread) {
        wrapper.classList.add("notif-item-unread");
      } else {
        wrapper.classList.remove("notif-item-unread");
      }

      listEl.appendChild(wrapper);
    });
  }

  // ===== API: ЛІСТ / MARK-READ =====

  function loadNotifications(opts = {}) {
    const { silent = false } = opts;
    if (isLoading) return;
    isLoading = true;
    if (!silent) setStatus("Завантаження нотифікацій…");

    const url = scope === "unread" ? "/api/notifications?scope=unread" : "/api/notifications?scope=all";

    return apiFetch(url)
      .then((data) => {
        items = data.items || [];
        unreadCount = data.unread_count || 0;
        renderList();
        updateCounter();
        if (!silent) {
          if (!items.length) {
            setStatus("Немає нотифікацій.", "info");
          } else {
            setStatus("Нотифікації оновлено.", "success");
          }
        }
      })
      .catch((err) => {
        console.error(err);
        setStatus(`Помилка завантаження: ${err.message}`, "error");
      })
      .finally(() => {
        isLoading = false;
      });
  }

  function markRead(id, { silent = false } = {}) {
    if (!id) return;
    apiFetch(`/api/notifications/${encodeURIComponent(id)}/read`, {
      method: "POST",
      body: JSON.stringify({}),
    })
      .then((data) => {
        const updated = data.item;
        unreadCount = data.unread_count ?? unreadCount;
        // оновимо локальний список
        items = items.map((n) =>
          String(n.id) === String(updated.id) ? { ...n, ...updated } : n
        );
        renderList();
        updateCounter();
        if (!silent) setStatus("Нотифікація позначена як прочитана.", "success");
      })
      .catch((err) => {
        console.error(err);
        if (!silent) setStatus(`Помилка: ${err.message}`, "error");
      });
  }

  function markAllRead() {
    apiFetch("/api/notifications/mark_all_read", {
      method: "POST",
      body: JSON.stringify({}),
    })
      .then((data) => {
        unreadCount = data.unread_count || 0;
        // всі read_at = now
        const nowIso = new Date().toISOString();
        items = items.map((n) => ({ ...n, read_at: n.read_at || nowIso }));
        renderList();
        updateCounter();
        setStatus("Усі нотифікації позначені як прочитані.", "success");
      })
      .catch((err) => {
        console.error(err);
        setStatus(`Помилка: ${err.message}`, "error");
      });
  }

  // ===== DROPDOWN (дзвіночок у навбарі) =====

  function openDropdown() {
    dropdownOpen = true;
    if (dropdownEl) dropdownEl.classList.add("notif-dropdown-open");
    // ліниве завантаження
    loadNotifications({ silent: true });
  }

  function closeDropdown() {
    dropdownOpen = false;
    if (dropdownEl) dropdownEl.classList.remove("notif-dropdown-open");
  }

  function toggleDropdown() {
    if (!dropdownEl) return;
    dropdownOpen ? closeDropdown() : openDropdown();
  }

  // клік по документу — закрити дропдаун, якщо клік поза ним
  if (dropdownEl) {
    document.addEventListener("click", (ev) => {
      if (!dropdownOpen) return;
      const target = ev.target;
      if (!target) return;
      // якщо клік був всередині dropdown або по дзвіночку — не закриваємо
      if (
        dropdownEl.contains(target) ||
        (bellEl && bellEl.contains(target))
      ) {
        return;
      }
      closeDropdown();
    });
  }

  // ===== ПОДІЇ UI =====

  if (filterEl) {
    filterEl.addEventListener("change", () => {
      const val = filterEl.value || "all";
      scope = val === "unread" ? "unread" : "all";
      loadNotifications();
    });
  }

  if (btnMarkAll) {
    btnMarkAll.addEventListener("click", () => {
      if (!items.length) {
        setStatus("Немає нотифікацій для позначення.", "info");
        return;
      }
      markAllRead();
    });
  }

  if (btnRefresh) {
    btnRefresh.addEventListener("click", () => {
      loadNotifications();
    });
  }

  if (bellEl && dropdownEl) {
    bellEl.addEventListener("click", (ev) => {
      ev.preventDefault();
      toggleDropdown();
    });
  }

  // ===== АВТОПОЛІНГ (опційно) =====

  function startPolling() {
    if (!autoPoll || pollTimer) return;
    pollTimer = window.setInterval(() => {
      // для бейджа достатньо scope=unread (але беремо current scope)
      loadNotifications({ silent: true });
    }, pollIntervalMs);
  }

  function stopPolling() {
    if (pollTimer) {
      window.clearInterval(pollTimer);
      pollTimer = null;
    }
  }

  // ===== ПУБЛІЧНИЙ API =====

  const api = {
    reload: () => loadNotifications(),
    loadUnreadSilent: () => {
      scope = "unread";
      if (filterEl) filterEl.value = "unread";
      return loadNotifications({ silent: true });
    },
    getItems: () => items.slice(),
    getUnreadCount: () => unreadCount,
    markRead,
    markAllRead,
    openDropdown,
    closeDropdown,
    toggleDropdown,
    startPolling,
    stopPolling,
  };

  // Збережемо в window, щоб інші скрипти могли пушити "локальні" тости, якщо треба
  // приклад:
  //   window.ProoflyNotify.toast("AI-завдання №123 завершено", "success");
  if (!window.ProoflyNotify) {
    window.ProoflyNotify = {};
  }
  window.ProoflyNotify.api = api;

  window.ProoflyNotify.toast = function toast(msg, level = "info") {
    // Простий фронтовий тост (без бекенду)
    let box = document.getElementById("toast-box");
    if (!box) {
      box = document.createElement("div");
      box.id = "toast-box";
      box.style.position = "fixed";
      box.style.right = "16px";
      box.style.bottom = "16px";
      box.style.zIndex = "9999";
      box.style.display = "flex";
      box.style.flexDirection = "column-reverse";
      box.style.gap = "6px";
      document.body.appendChild(box);
    }
    const el = document.createElement("div");
    el.style.minWidth = "220px";
    el.style.maxWidth = "320px";
    el.style.borderRadius = "10px";
    el.style.padding = "8px 10px";
    el.style.fontSize = "13px";
    el.style.display = "flex";
    el.style.alignItems = "center";
    el.style.gap = "6px";
    el.style.border = "1px solid #1f2937";
    el.style.background = "#020617";
    el.style.boxShadow = "0 8px 20px rgba(0,0,0,.45)";
    el.style.cursor = "default";

    const icon = levelIcon(level);
    const color =
      level === "success"
        ? "#4ade80"
        : level === "warning"
        ? "#facc15"
        : level === "error"
        ? "#f97373"
        : "#60a5fa";

    el.innerHTML = `
      <span style="font-size:16px;">${icon}</span>
      <span style="flex:1;color:#e5e7eb;">${escapeHtml(msg)}</span>
    `;
    el.style.borderColor = color;

    box.appendChild(el);

    setTimeout(() => {
      el.style.opacity = "0";
      el.style.transform = "translateY(4px)";
      el.style.transition = "opacity .25s, transform .25s";
      setTimeout(() => el.remove(), 260);
    }, 3500);
  };

  // ===== СТАРТ =====

  // Якщо є список (повна сторінка) – одразу завантажуємо
  if (listEl) {
    loadNotifications();
  } else {
    // Якщо тільки бейдж у шапці – тихо загрузимо unread, щоб був рахунок
    loadNotifications({ silent: true });
  }

  if (autoPoll) {
    startPolling();
  }

  return api;
}
