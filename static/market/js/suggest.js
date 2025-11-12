// static/market/js/suggest.js
// Пошукові підказки для STL-маркету Proofly

(function () {
  const DEBOUNCE_MS = 220;
  const MIN_QUERY_LEN = 2;

  let inputEl;
  let boxEl;
  let activeIndex = -1;
  let items = [];
  let debounceTimer = null;

  function qs(sel, root) {
    return (root || document).querySelector(sel);
  }

  function qsa(sel, root) {
    return Array.from((root || document).querySelectorAll(sel));
  }

  function showBox() {
    if (!boxEl) return;
    if (!items.length) {
      boxEl.style.display = "none";
      return;
    }
    boxEl.style.display = "block";
  }

  function hideBox() {
    if (!boxEl) return;
    boxEl.style.display = "none";
    boxEl.innerHTML = "";
    items = [];
    activeIndex = -1;
  }

  function setActive(idx) {
    activeIndex = idx;
    qsa(".suggest-item", boxEl).forEach((el, i) => {
      el.classList.toggle("active", i === idx);
    });
  }

  function applySuggestion(item) {
    if (!inputEl || !item) return;
    inputEl.value = item.query || item.text || "";
    hideBox();

    // Автоматично запускаємо пошук, якщо є кнопка
    const btn = qs("#btn-search");
    if (btn) {
      btn.click();
    } else {
      // або просто сабмітимо форму, якщо вона є
      const form = inputEl.form;
      if (form) form.submit();
    }
  }

  function renderItems() {
    if (!boxEl) return;

    boxEl.innerHTML = "";

    if (!items.length) {
      const empty = document.createElement("div");
      empty.className = "suggest-empty muted";
      empty.textContent = "Немає підказок. Спробуй інші слова.";
      boxEl.appendChild(empty);
      boxEl.style.display = "block";
      return;
    }

    items.forEach((item, idx) => {
      const el = document.createElement("div");
      el.className = "suggest-item";
      el.setAttribute("data-idx", String(idx));

      const label = item.label || item.text || item.query || "";

      el.textContent = label;

      if (item.hint) {
        const span = document.createElement("span");
        span.className = "suggest-hint";
        span.textContent = " " + item.hint;
        el.appendChild(span);
      }

      el.addEventListener("mousedown", (e) => {
        e.preventDefault(); // щоб blur інпута не закрив список раніше
        applySuggestion(item);
      });

      boxEl.appendChild(el);
    });

    activeIndex = -1;
    showBox();
  }

  async function fetchSuggestions(query) {
    if (!query || query.length < MIN_QUERY_LEN) {
      hideBox();
      return;
    }

    // endpoint можна потім змінити на конфіг, зараз дефолтний
    const endpoint = boxEl.getAttribute("data-endpoint") || "/api/market/suggest";
    const url = `${endpoint}?q=${encodeURIComponent(query)}`;

    try {
      const res = await fetch(url, { method: "GET" });
      if (!res.ok) throw new Error("Bad status " + res.status);
      const data = await res.json();

      // Очікуваний формат:
      //   { items: [ { query, label, hint }, ... ] }
      // або просто масив строк
      if (Array.isArray(data)) {
        items = data.map((q) => ({ query: q, label: q }));
      } else {
        items = Array.isArray(data.items)
          ? data.items
          : [];
      }

      renderItems();
    } catch (err) {
      console.error("suggest: error fetching suggestions", err);
      // невеликий м’який фейл
      hideBox();
    }
  }

  function onInputChange() {
    const val = inputEl.value.trim();

    if (debounceTimer) {
      clearTimeout(debounceTimer);
      debounceTimer = null;
    }

    if (!val || val.length < MIN_QUERY_LEN) {
      hideBox();
      return;
    }

    debounceTimer = setTimeout(() => {
      fetchSuggestions(val);
    }, DEBOUNCE_MS);
  }

  function onKeyDown(e) {
    if (!items.length || boxEl.style.display === "none") return;

    if (e.key === "ArrowDown") {
      e.preventDefault();
      if (activeIndex < items.length - 1) {
        setActive(activeIndex + 1);
      } else {
        setActive(0);
      }
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      if (activeIndex > 0) {
        setActive(activeIndex - 1);
      } else {
        setActive(items.length - 1);
      }
    } else if (e.key === "Enter") {
      if (activeIndex >= 0 && activeIndex < items.length) {
        e.preventDefault();
        applySuggestion(items[activeIndex]);
      }
    } else if (e.key === "Escape") {
      hideBox();
    }
  }

  function init() {
    inputEl = qs("#q");
    boxEl = qs("#search-suggest");

    if (!inputEl || !boxEl) return;

    inputEl.setAttribute("autocomplete", "off");

    inputEl.addEventListener("input", onInputChange);
    inputEl.addEventListener("keydown", onKeyDown);

    // Якщо клік поза інпутом/підказками — ховаємо
    document.addEventListener("click", (e) => {
      if (!boxEl) return;
      const target = e.target;
      if (target === inputEl || boxEl.contains(target)) return;
      hideBox();
    });

    // Якщо при загрузці в інпуті вже є q — можна один раз спробувати
    const initial = inputEl.value.trim();
    if (initial.length >= MIN_QUERY_LEN) {
      fetchSuggestions(initial);
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
