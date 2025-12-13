// static/js/stats_charts.js
// Графіки адмін-статистики для Proofly STL.
//
// Працює разом із stats.html та бекендом analytics.py.
//
// Очікувані ендпоінти (ми їх зробимо в analytics.py):
//   GET /api/analytics/series?metric=visitors&days=30
//   GET /api/analytics/series?metric=signups&days=30
//   GET /api/analytics/series?metric=models&days=30
//
// Відповідь:
//   {
//     ok: true,
//     metric: "visitors",
//     days: 30,
//     points: [
//       { date: "2025-11-01", value: 123 },
//       ...
//     ]
//   }
//
// HTML (у stats.html можна робити щось таке):
//   <canvas id="stats-visitors"></canvas>
//   <canvas id="stats-signups"></canvas>
//   <canvas id="stats-models"></canvas>
//   <select id="stats-range">...</select>
//   <div id="stats-status"></div>
//
// І потім:
//   <script type="module">
//     import { initStatsCharts } from "{{ url_for('static', filename='js/stats_charts.js') }}";
//     document.addEventListener("DOMContentLoaded", () => {
//       initStatsCharts();
//     });
//   </script>

export function initStatsCharts({
  visitorsCanvasId = "stats-visitors",
  signupsCanvasId = "stats-signups",
  modelsCanvasId = "stats-models",
  rangeSelectId = "stats-range",
  statusId = "stats-status",
} = {}) {
  const $ = (id) => (id ? document.getElementById(id) : null);

  const visitorsCanvas = $(visitorsCanvasId);
  const signupsCanvas = $(signupsCanvasId);
  const modelsCanvas = $(modelsCanvasId);
  const rangeSelect = $(rangeSelectId);
  const statusEl = $(statusId);

  const charts = {
    visitors: null,
    signups: null,
    models: null,
  };

  let currentDays = 30;
  let isLoading = false;

  // ========= УТИЛІТИ =========

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
      credentials: "same-origin",
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

  function ensureChartJs() {
    if (typeof window === "undefined" || !window.Chart) {
      console.warn("[stats_charts] Chart.js не знайдено (window.Chart). Перевір, чи підключений CDN у stats.html.");
      setStatus(
        "Chart.js не підключений. Додай CDN <script src=\"https://cdn.jsdelivr.net/npm/chart.js\"></script> у stats.html.",
        "error"
      );
      return false;
    }
    return true;
  }

  function buildLineChart(canvas, label, points, colorKey) {
    if (!canvas || !ensureChartJs()) return null;

    const ctx = canvas.getContext("2d");
    if (!ctx) return null;

    const labels = points.map((p) => p.date);
    const values = points.map((p) => p.value || 0);

    const c = window.getComputedStyle(document.documentElement);
    const ink = c.getPropertyValue("--ink") || "#e5e7eb";
    const lineColor =
      colorKey === "green"
        ? "#22c55e"
        : colorKey === "amber"
        ? "#facc15"
        : "#60a5fa";

    const data = {
      labels,
      datasets: [
        {
          label,
          data: values,
          borderColor: lineColor,
          backgroundColor: "rgba(37, 99, 235, 0.1)",
          borderWidth: 2,
          tension: 0.3,
          pointRadius: 2,
          pointHitRadius: 6,
        },
      ],
    };

    const options = {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: {
          labels: {
            color: ink,
            font: { size: 11 },
          },
        },
        tooltip: {
          intersect: false,
          mode: "index",
        },
      },
      scales: {
        x: {
          ticks: {
            color: "#9ca3af",
            maxRotation: 0,
            autoSkip: true,
          },
          grid: {
            display: false,
          },
        },
        y: {
          ticks: {
            color: "#9ca3af",
            precision: 0,
          },
          grid: {
            color: "rgba(55,65,81,0.4)",
          },
        },
      },
    };

    return new window.Chart(ctx, {
      type: "line",
      data,
      options,
    });
  }

  function destroyChart(chart) {
    if (chart && typeof chart.destroy === "function") {
      chart.destroy();
    }
  }

  // ========= ЗАВАНТАЖЕННЯ ДАНИХ =========

  function loadMetric(metric) {
    const url = `/api/analytics/series?metric=${encodeURIComponent(
      metric
    )}&days=${encodeURIComponent(currentDays)}`;
    return apiFetch(url).then((data) => {
      const pts = data.points || [];
      return { metric, points: pts };
    });
  }

  function loadAllMetrics() {
    if (isLoading) return;
    isLoading = true;
    setStatus("Завантаження даних за останні " + currentDays + " днів…");

    const promises = [];

    if (visitorsCanvas) promises.push(loadMetric("visitors"));
    if (signupsCanvas) promises.push(loadMetric("signups"));
    if (modelsCanvas) promises.push(loadMetric("models"));

    if (!promises.length) {
      setStatus("Немає жодного графіка для відображення (canvas не знайдені).", "error");
      isLoading = false;
      return;
    }

    Promise.all(promises)
      .then((results) => {
        results.forEach(({ metric, points }) => {
          if (metric === "visitors" && visitorsCanvas) {
            destroyChart(charts.visitors);
            charts.visitors = buildLineChart(
              visitorsCanvas,
              `Відвідувачі за ${currentDays} днів`,
              points,
              "blue"
            );
          }
          if (metric === "signups" && signupsCanvas) {
            destroyChart(charts.signups);
            charts.signups = buildLineChart(
              signupsCanvas,
              `Нові акаунти за ${currentDays} днів`,
              points,
              "green"
            );
          }
          if (metric === "models" && modelsCanvas) {
            destroyChart(charts.models);
            charts.models = buildLineChart(
              modelsCanvas,
              `Нові моделі за ${currentDays} днів`,
              points,
              "amber"
            );
          }
        });

        setStatus("Графіки оновлено.", "success");
      })
      .catch((err) => {
        console.error(err);
        setStatus(`Помилка завантаження статистики: ${err.message}`, "error");
      })
      .finally(() => {
        isLoading = false;
      });
  }

  // ========= ПОДІЇ =========

  if (rangeSelect) {
    rangeSelect.addEventListener("change", () => {
      const val = rangeSelect.value || "30";
      const n = parseInt(val, 10);
      currentDays = Number.isFinite(n) && n > 0 ? n : 30;
      loadAllMetrics();
    });
  }

  // ========= СТАРТ =========

  // Якщо ні одного canvas немає — тихо виходимо
  if (!visitorsCanvas && !signupsCanvas && !modelsCanvas) {
    console.warn("[stats_charts] Не знайдено жодного canvas для графіків.");
    return {
      reload: () => {},
      setDays: () => {},
    };
  }

  loadAllMetrics();

  // Повертаємо невелике API, якщо раптом захочеш керувати з інших скриптів
  return {
    reload: loadAllMetrics,
    setDays(days) {
      const n = parseInt(days, 10);
      if (!Number.isFinite(n) || n <= 0) return;
      currentDays = n;
      if (rangeSelect) {
        rangeSelect.value = String(n);
      }
      loadAllMetrics();
    },
  };
}
