// static/market/js/bundle_cart.js
// Локальний кошик + бандли для Proofly STL Market

(function () {
  const CART_KEY = "proofly_cart_v1";

  function qs(sel, root) {
    return (root || document).querySelector(sel);
  }

  function qsa(sel, root) {
    return Array.from((root || document).querySelectorAll(sel));
  }

  /* ==================== CART MODEL ==================== */

  function loadCart() {
    try {
      const raw = localStorage.getItem(CART_KEY);
      if (!raw) return { items: [], bundles: [] };
      const obj = JSON.parse(raw);
      if (!obj || typeof obj !== "object") {
        return { items: [], bundles: [] };
      }
      if (!Array.isArray(obj.items)) obj.items = [];
      if (!Array.isArray(obj.bundles)) obj.bundles = [];
      return obj;
    } catch (e) {
      console.warn("cart: cannot parse localStorage", e);
      return { items: [], bundles: [] };
    }
  }

  function saveCart(cart) {
    try {
      localStorage.setItem(CART_KEY, JSON.stringify(cart));
    } catch (e) {
      console.warn("cart: cannot save", e);
    }
    updateCartBadges(cart);
  }

  function findItem(cart, itemId) {
    return cart.items.find((x) => String(x.id) === String(itemId));
  }

  function findBundle(cart, bundleId) {
    return cart.bundles.find((x) => String(x.id) === String(bundleId));
  }

  function addItem(cart, payload) {
    const id = payload.id;
    if (!id) return cart;

    let item = findItem(cart, id);
    if (!item) {
      item = {
        id: id,
        title: payload.title || "",
        price: payload.price != null ? Number(payload.price) : 0,
        thumb: payload.thumb || "",
        qty: 1,
      };
      cart.items.push(item);
    } else {
      item.qty = (item.qty || 1) + 1;
    }
    return cart;
  }

  function removeItem(cart, itemId) {
    cart.items = cart.items.filter((x) => String(x.id) !== String(itemId));
    return cart;
  }

  function addBundle(cart, payload) {
    const id = payload.id;
    if (!id) return cart;

    let bundle = findBundle(cart, id);
    if (!bundle) {
      bundle = {
        id: id,
        title: payload.title || "",
        price: payload.price != null ? Number(payload.price) : 0,
        discount: payload.discount != null ? Number(payload.discount) : 0,
        items: payload.items || [],
        thumb: payload.thumb || "",
        qty: 1,
      };
      cart.bundles.push(bundle);
    } else {
      bundle.qty = (bundle.qty || 1) + 1;
    }
    return cart;
  }

  function removeBundle(cart, bundleId) {
    cart.bundles = cart.bundles.filter((x) => String(x.id) !== String(bundleId));
    return cart;
  }

  function clearCart(cart) {
    cart.items = [];
    cart.bundles = [];
    return cart;
  }

  function computeTotals(cart) {
    let countItems = 0;
    let sum = 0;

    cart.items.forEach((it) => {
      const qty = it.qty || 1;
      const price = it.price != null ? Number(it.price) : 0;
      countItems += qty;
      sum += price * qty;
    });

    cart.bundles.forEach((b) => {
      const qty = b.qty || 1;
      const price = b.price != null ? Number(b.price) : 0;
      countItems += qty;
      sum += price * qty;
    });

    return { countItems, sum };
  }

  /* ==================== UI UPDATERS ==================== */

  function updateCartBadges(cart) {
    const totals = computeTotals(cart);
    qsa("[data-cart-count]").forEach((el) => {
      el.textContent = String(totals.countItems || 0);
    });
    qsa("[data-cart-sum]").forEach((el) => {
      el.textContent = (totals.sum || 0).toFixed(2);
    });
  }

  function showToast(message) {
    // М’який варіант — без бібліотек, мінімальний тост
    let box = qs("#cart-toast");
    if (!box) {
      box = document.createElement("div");
      box.id = "cart-toast";
      box.style.position = "fixed";
      box.style.right = "16px";
      box.style.bottom = "16px";
      box.style.zIndex = "9999";
      box.style.maxWidth = "260px";
      box.style.padding = "10px 12px";
      box.style.borderRadius = "10px";
      box.style.background = "rgba(15, 17, 25, 0.96)";
      box.style.border = "1px solid rgba(80, 90, 120, 0.9)";
      box.style.fontSize = "13px";
      box.style.color = "#e8eaed";
      box.style.boxShadow = "0 6px 26px rgba(0,0,0,0.7)";
      box.style.opacity = "0";
      box.style.transition = "opacity 0.2s ease-out, transform 0.2s ease-out";
      box.style.transform = "translateY(10px)";
      document.body.appendChild(box);
    }
    box.textContent = message;
    requestAnimationFrame(() => {
      box.style.opacity = "1";
      box.style.transform = "translateY(0)";
    });
    setTimeout(() => {
      box.style.opacity = "0";
      box.style.transform = "translateY(10px)";
    }, 2000);
  }

  /* ==================== EVENT HANDLERS ==================== */

  function handleAddToCartClick(e) {
    const btn = e.target.closest("[data-action='add-to-cart']");
    if (!btn) return;

    const itemId = btn.getAttribute("data-id");
    if (!itemId) return;

    const title = btn.getAttribute("data-title") || "";
    const thumb = btn.getAttribute("data-thumb") || "";
    const priceStr = btn.getAttribute("data-price");
    const price = priceStr != null ? Number(priceStr) : 0;

    let cart = loadCart();
    cart = addItem(cart, { id: itemId, title, thumb, price });
    saveCart(cart);

    showToast("Модель додана в кошик 🧩");
  }

  function handleAddBundleClick(e) {
    const btn = e.target.closest("[data-action='add-bundle']");
    if (!btn) return;

    const bundleId = btn.getAttribute("data-bundle-id");
    if (!bundleId) return;

    const title = btn.getAttribute("data-title") || "Bundle";
    const thumb = btn.getAttribute("data-thumb") || "";
    const priceStr = btn.getAttribute("data-price");
    const discountStr = btn.getAttribute("data-discount");
    const price = priceStr != null ? Number(priceStr) : 0;
    const discount = discountStr != null ? Number(discountStr) : 0;

    // Список item_id всередині бандла (через кому)
    const itemsRaw = btn.getAttribute("data-items") || "";
    const items = itemsRaw
      .split(",")
      .map((s) => s.trim())
      .filter(Boolean);

    let cart = loadCart();
    cart = addBundle(cart, {
      id: bundleId,
      title,
      thumb,
      price,
      discount,
      items,
    });
    saveCart(cart);

    showToast("Бандл додано в кошик 🎁");
  }

  function handleCartButtons(e) {
    // Кнопки типу "видалити з кошика", якщо у тебе є сторінка /cart
    const btnRemoveItem = e.target.closest("[data-action='remove-cart-item']");
    const btnRemoveBundle = e.target.closest("[data-action='remove-cart-bundle']");
    const btnClear = e.target.closest("[data-action='clear-cart']");

    let cart;

    if (btnRemoveItem) {
      const id = btnRemoveItem.getAttribute("data-id");
      if (!id) return;
      cart = loadCart();
      cart = removeItem(cart, id);
      saveCart(cart);
      // опціонально — видалити елемент зі сторінки
      const row = btnRemoveItem.closest("[data-cart-row]");
      if (row) row.remove();
      showToast("Товар видалений з кошика");
    }

    if (btnRemoveBundle) {
      const id = btnRemoveBundle.getAttribute("data-bundle-id");
      if (!id) return;
      cart = loadCart();
      cart = removeBundle(cart, id);
      saveCart(cart);
      const row = btnRemoveBundle.closest("[data-cart-row]");
      if (row) row.remove();
      showToast("Бандл видалений з кошика");
    }

    if (btnClear) {
      cart = loadCart();
      cart = clearCart(cart);
      saveCart(cart);
      // Можна зробити повне оновлення сторінки /cart
      if (btnClear.getAttribute("data-reload") === "1") {
        window.location.reload();
      } else {
        showToast("Кошик очищено");
      }
    }
  }

  /* ==================== BUNDLE BUILDER (опціонально) ==================== */

  function initBundleBuilder() {
    const builder = qs("#bundle-builder");
    if (!builder) return;

    // Очікувана структура:
    // <div id="bundle-builder" data-bundle-id="..." data-title="..." data-price="...">
    //   <input type="checkbox" data-item-id="..." data-price="...">
    //   ...
    //   <span data-bundle-total></span>
    // </div>

    const checkboxes = qsa("input[type='checkbox'][data-item-id]", builder);
    const totalEl = qs("[data-bundle-total]", builder);

    function recalc() {
      let sum = 0;
      checkboxes.forEach((ch) => {
        if (!ch.checked) return;
        const pStr = ch.getAttribute("data-price");
        const price = pStr != null ? Number(pStr) : 0;
        sum += price;
      });
      if (totalEl) {
        totalEl.textContent = sum.toFixed(2) + " zł";
      }
    }

    checkboxes.forEach((ch) => {
      ch.addEventListener("change", recalc);
    });

    recalc();

    // Кнопка "створити бандл" (опціонально)
    const createBtn = qs("[data-action='create-bundle-from-builder']", builder);
    if (createBtn) {
      createBtn.addEventListener("click", () => {
        const bundleId = builder.getAttribute("data-bundle-id") || "custom";
        const title = builder.getAttribute("data-title") || "Custom bundle";
        const thumb = builder.getAttribute("data-thumb") || "";

        const selectedIds = checkboxes
          .filter((ch) => ch.checked)
          .map((ch) => ch.getAttribute("data-item-id"))
          .filter(Boolean);

        if (!selectedIds.length) {
          showToast("Вибери хоча б 1 модель для бандла");
          return;
        }

        let sum = 0;
        checkboxes.forEach((ch) => {
          if (!ch.checked) return;
          const pStr = ch.getAttribute("data-price");
          const price = pStr != null ? Number(pStr) : 0;
          sum += price;
        });

        // Можна зробити невелику знижку за кастом-бандл, наприклад 10%
        const discount = 0.1;
        const bundlePrice = sum * (1 - discount);

        let cart = loadCart();
        cart = addBundle(cart, {
          id: bundleId,
          title,
          thumb,
          price: bundlePrice,
          discount: discount * 100,
          items: selectedIds,
        });
        saveCart(cart);

        showToast("Кастомний бандл додано в кошик 🎁");
      });
    }
  }

  /* ==================== EXPORT TO SERVER (опціонально) ==================== */

  async function syncCartToServer() {
    // Якщо захочеш мати серверний кошик — можна викликати це при логіні.
    const endpoint = "/api/market/cart/sync"; // реалізуєш потім на бекенді
    const cart = loadCart();

    try {
      await fetch(endpoint, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify(cart),
      });
    } catch (err) {
      console.warn("cart: sync to server failed", err);
    }
  }

  /* ==================== INIT ==================== */

  function init() {
    const cart = loadCart();
    updateCartBadges(cart);

    document.addEventListener("click", (e) => {
      handleAddToCartClick(e);
      handleAddBundleClick(e);
      handleCartButtons(e);
    });

    initBundleBuilder();

    // Якщо треба — можна викликати syncCartToServer() при певних умовах
    // (наприклад, якщо є глобальний currentUserId)
    // if (window.currentUserId) {
    //   syncCartToServer();
    // }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
