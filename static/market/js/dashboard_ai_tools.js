// static/js/dashboard_ai_tools.js
// Адмінський дашборд для AI-інструментів Proofly STL.
//
// Очікувані API (можна буде реалізувати в ai_api.py / worker.py):
//
//   GET /api/ai/tools_stats
//     -> {
//          ok:true,
//          items:[
//            {
//              key: "printability",
//              name: "Printability Check",
//              category: "stl",
//              used_count: 152,
//              last_used_at: "2025-11-10T12:34:56Z",
//              avg_latency_ms: 2400,
//              error_rate: 0.03,
//              credits_spent: 1234
//            }, ...
//          ],
//          totals: {
//            used_count: 1234,
//            credits_spent: 9999,
//            jobs_running: 2
//          }
//        }
//
//   GET /api/ai/jobs_recent?limit=30
//     -> {
//          ok:true,
//          items:[
//            {
//              id: "job_123",
//              tool_key: "printability",
//              tool_name: "Printability Check",
//              status: "done|running|queued|error",
//              created_at: "2025-11-10T12:34:56Z",
//              finished_at: "2025-11-10T12:36:12Z",
//              duration_ms: 76000,
//              input_brief: "Dragon v2.stl",
//              error_msg: null
//            }, ...
//        }
//
// HTML-хуки (у admin/stats.html чи окремій сторінці):
//
//   <div id="ai-dash-toolbar"> ... кнопки, фільтри ... </div>
//   <div id="ai-dash-status"></div>
//
//   <div id="ai-dash-cards">
//     <!-- всередині JS сам зробить карточки по інструментах -->
//   </div>
//
//   <table>
//     <tbody id="ai-dash-jobs"></tbody>
//   </table>
//
//   <select id="ai-dash-filter-tool"></select>
//   <select id="ai-dash-filter-status"></select>
//   <button id="ai-dash-refresh">Оновити</button>
//   <button id="ai-dash-stop-running">Зупинити всі завислі</button> (опціонально)
//
// Потім у шаблоні:
//
//   <script type="module">
//     import { initAiToolsDashboard } from "{{ url_for('static', filename='js/dashboard_ai_tools.js') }}";
//     document.addEventListener("DOMContentLoaded", () => {
//       initAiToolsDashboard();
//     });
//   </script>

export function initAiToolsDashboard({
  cardsContainerId = "ai-dash-cards",
  jobsTbodyId = "ai-dash-jobs",
  statusId = "ai-dash-status",
  filterToolId = "ai-dash-filter-tool",
  filterStatusId = "ai-dash-filter-status",
  refreshBtnId = "ai-dash-refresh",
  stopRunningBtnId = "ai-dash-stop-running", // опціонально, бекенд можемо додати пізніше
} = {}) {
  const $ = (id) => (id ? document.getElementById(id) : null);

  const cardsEl = $(cardsContainerId);
  const jobsEl = $(jobsTbodyId);
  const statusEl = $(statusId);
  const filterToolEl = $(filterToolId);
  const filterStatusEl = $(filterStatusId);
  const refreshBtn = $(refreshBtnId);
  const stopRunningBtn = $(stopRunningBtnId);

  let toolsStats = [];
  let jobs = [];
  let isLoading = false;

  // ================= УТИЛІТИ =================

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

  function fmtMs(ms) {
    if (ms == null) return "—";
    const s = ms / 1000;
    if (s < 60) return `${Math.round(s)} с`;
    const m = Math.round(s / 60);
    return `${m} хв`;
  }

  function statusPill(status) {
    const s = (status || "").toLowerCase();
    if (s === "done" || s === "success") return '<span class="ai-pill ai-pill-ok">Готово</span>';
    if (s === "running") return '<span class="ai-pill ai-pill-run">Виконується</span>';
    if (s === "queued") return '<span class="ai-pill ai-pill-queue">В черзі</span>';
    if (s === "error") return '<span class="ai-pill ai-pill-err">Помилка</span>';
    return `<span class="ai-pill">${escapeHtml(status || "—")}</span>`;
  }

  // ================= РЕНДЕР КАРТОК ПО ІНСТРУМЕНТАХ =================

  function renderCards() {
    if (!cardsEl) return;

    cardsEl.innerHTML = "";

    if (!toolsStats || !toolsStats.length) {
      const div = document.createElement("div");
      div.style.fontSize = "13px";
      div.style.opacity = "0.8";
      div.textContent = "Поки що немає даних про використання AI-інструментів.";
      cardsEl.appendChild(div);
      return;
    }

    toolsStats.forEach((tool) => {
      const card = document.createElement("div");
      card.className = "ai-tool-card";

      const usedCount = tool.used_count || 0;
      const avgLatMs = tool.avg_latency_ms || 0;
      const errorRate = tool.error_rate || 0;
      const lastUsed = tool.last_used_at ? timeAgo(tool.last_used_at) : "ще не використовувався";
      const credits = tool.credits_spent || 0;

      const catLabel =
        tool.category === "stl"
          ? "STL/3D"
          : tool.category === "image"
          ? "Зображення"
          : tool.category === "text"
          ? "Текст"
          : tool.category || "Інше";

      const errPercent = (errorRate * 100).toFixed(1);

      card.innerHTML = `
        <div class="ai-tool-card-header">
          <div>
            <div class="ai-tool-name">${escapeHtml(tool.name || tool.key || "AI Tool")}</div>
            <div class="ai-tool-meta">
              <span>${escapeHtml(tool.key || "")}</span>
              <span>·</span>
              <span>${escapeHtml(catLabel)}</span>
            </div>
          </div>
          <div class="ai-tool-pill">AI</div>
        </div>

        <div class="ai-tool-metrics">
          <div class="ai-tool-metric">
            <div class="ai-tool-metric-label">Запусків</div>
            <div class="ai-tool-metric-value">${usedCount}</div>
          </div>
          <div class="ai-tool-metric">
            <div class="ai-tool-metric-label">Сер. час</div>
            <div class="ai-tool-metric-value">${fmtMs(avgLatMs)}</div>
          </div>
          <div class="ai-tool-metric">
            <div class="ai-tool-metric-label">Помилки</div>
            <div class="ai-tool-metric-value">${errPercent}%</div>
          </div>
          <div class="ai-tool-metric">
            <div class="ai-tool-metric-label">PXP / кредити</div>
            <div class="ai-tool-metric-value">${credits}</div>
          </div>
        </div>

        <div class="ai-tool-footer">
          <span class="ai-tool-last">Останній запуск: ${escapeHtml(lastUsed)}</span>
        </div>
      `;

      cardsEl.appendChild(card);
    });
  }

  // ================= РЕНДЕР ТАБЛИЦІ JOBS =================

  function buildToolOptions() {
    if (!filterToolEl) return;
    const keys = Array.from(new Set(toolsStats.map((t) => t.key).filter(Boolean)));

    // зберігаємо поточний вибір
    const prev = filterToolEl.value || "";

    filterToolEl.innerHTML =
      '<option value="">Всі інструменти</option>' +
      keys
        .map(
          (k) =>
            `<option value="${escapeHtml(k)}"${prev === k ? " selected" : ""}>${escapeHtml(
              k
            )}</option>`
        )
        .join("");
  }

  function renderJobs() {
    if (!jobsEl) return;

    jobsEl.innerHTML = "";

    if (!jobs || !jobs.length) {
      const tr = document.createElement("tr");
      const td = document.createElement("td");
      td.colSpan = 5;
      td.style.fontSize = "13px";
      td.style.opacity = "0.8";
      td.style.padding = "6px 4px";
      td.textContent =
        "Поки немає запущених AI-задач. Як тільки користувачі запустять Printability / AI-фічі — вони зʼявляться тут.";
      tr.appendChild(td);
      jobsEl.appendChild(tr);
      return;
    }

    const filterTool = filterToolEl ? filterToolEl.value : "";
    const filterStatus = filterStatusEl ? filterStatusEl.value : "";

    let filtered = jobs.slice();
    if (filterTool) {
      filtered = filtered.filter((j) => (j.tool_key || "") === filterTool);
    }
    if (filterStatus) {
      filtered = filtered.filter(
        (j) => (j.status || "").toLowerCase() === filterStatus.toLowerCase()
      );
    }

    if (!filtered.length) {
      const tr = document.createElement("tr");
      const td = document.createElement("td");
      td.colSpan = 5;
      td.style.fontSize = "13px";
      td.style.opacity = "0.8";
      td.style.padding = "6px 4px";
      td.textContent = "Немає задач, що підпадають під обрані фільтри.";
      tr.appendChild(td);
      jobsEl.appendChild(tr);
      return;
    }

    filtered.forEach((job) => {
      const tr = document.createElement("tr");
      tr.className = "ai-job-row";

      const toolName =
        job.tool_name || toolsStats.find((t) => t.key === job.tool_key)?.name || job.tool_key;

      const created = job.created_at ? timeAgo(job.created_at) : "—";
      const dur = fmtMs(job.duration_ms);
      const inputShort = (job.input_brief || "").slice(0, 80);

      tr.innerHTML = `
        <td class="ai-job-cell ai-job-cell-tool">
          <div class="ai-job-tool">${escapeHtml(toolName || "AI Tool")}</div>
          <div class="ai-job-tool-key">${escapeHtml(job.tool_key || "")}</div>
        </td>
        <td class="ai-job-cell ai-job-cell-input">
          <div class="ai-job-input">${escapeHtml(inputShort || "—")}</div>
        </td>
        <td class="ai-job-cell ai-job-cell-status">
          ${statusPill(job.status)}
        </td>
        <td class="ai-job-cell ai-job-cell-time">
          <div>${escapeHtml(created)}</div>
          <div class="ai-job-duration">${escapeHtml(dur)}</div>
        </td>
        <td class="ai-job-cell ai-job-cell-error">
          ${
            job.error_msg
              ? `<span title="${escapeHtml(job.error_msg)}">⚠ ${escapeHtml(
                  job.error_msg.slice(0, 40)
                )}${job.error_msg.length > 40 ? "…" : ""}</span>`
              : ""
          }
        </td>
      `;
      jobsEl.appendChild(tr);
    });
  }

  // ================= ЗАВАНТАЖЕННЯ ДАНИХ =================

  function loadAll() {
    if (isLoading) return;
    isLoading = true;
    setStatus("Завантаження статистики AI-інструментів…");

    const p1 = apiFetch("/api/ai/tools_stats").catch((err) => {
      console.error(err);
      throw new Error("tools_stats: " + err.message);
    });

    const p2 = apiFetch("/api/ai/jobs_recent?limit=30").catch((err) => {
      console.error(err);
      throw new Error("jobs_recent: " + err.message);
    });

    return Promise.all([p1, p2])
      .then(([toolsData, jobsData]) => {
        toolsStats = toolsData.items || [];
        jobs = jobsData.items || [];

        renderCards();
        buildToolOptions();
        renderJobs();

        setStatus("AI-дашборд оновлено.", "success");
      })
      .catch((err) => {
        console.error(err);
        setStatus(`Помилка завантаження AI-статистики: ${err.message}`, "error");
        if (window.ProoflyNotify && window.ProoflyNotify.toast) {
          window.ProoflyNotify.toast(
            "Не вдалося оновити AI-дашборд: " + err.message,
            "error"
          );
        }
      })
      .finally(() => {
        isLoading = false;
      });
  }

  // ================= ДОДАТКОВЕ: ЗУПИНКА ЗАВИСЛИХ JOBS =================

  function stopRunningJobs() {
    // Це опційна фіча: можна зробити бекенд POST /api/ai/jobs/stop_running.
    // Поки що просто заглушка, щоб не ламати фронт.
    if (!stopRunningBtn) return;
    if (!window.confirm("Зупинити всі jobs зі статусом 'running'?")) {
      return;
    }
    apiFetch("/api/ai/jobs/stop_running", {
      method: "POST",
      body: JSON.stringify({}),
    })
      .then(() => {
        setStatus("Запит на зупинку jobs відправлено. Оновлюємо список…", "success");
        return loadAll();
      })
      .catch((err) => {
        console.error(err);
        setStatus(`Помилка при зупинці jobs: ${err.message}`, "error");
      });
  }

  // ================= ПОДІЇ =================

  if (refreshBtn) {
    refreshBtn.addEventListener("click", () => {
      loadAll();
    });
  }

  if (stopRunningBtn) {
    stopRunningBtn.addEventListener("click", () => {
      stopRunningJobs();
    });
  }

  if (filterToolEl) {
    filterToolEl.addEventListener("change", () => {
      renderJobs();
    });
  }

  if (filterStatusEl) {
    filterStatusEl.addEventListener("change", () => {
      renderJobs();
    });
  }

  // ================= СТАРТ =================

  // Якщо немає ні cardsEl, ні jobsEl — немає сенсу ініціалізувати
  if (!cardsEl && !jobsEl) {
    console.warn("[dashboard_ai_tools] Немає елементів для рендеру дашборда.");
    return {
      reload: () => {},
      getTools: () => [],
      getJobs: () => [],
    };
  }

  loadAll();

  // Публічне API (можна викликати з консолі admin)
  const api = {
    reload: loadAll,
    getTools: () => toolsStats.slice(),
    getJobs: () => jobs.slice(),
  };

  if (!window.ProoflyAdmin) window.ProoflyAdmin = {};
  window.ProoflyAdmin.aiDashboard = api;

  return api;
}
