// static/js/stl_ui.js
// Вкладки, горизонтальний скрол стрілками, та модальне вікно "Експорт"

export function initUI() {
  initTabs('leftTabs', 'stl_left_panel');
  initTabs('stlTabs',  'stl_right_panel');
  wireArrows('leftTabs');
  wireArrows('stlTabs');
  initExportModal();
}

/* ========== Tabs ========== */
function initTabs(containerId, storageKey) {
  const wrap = document.getElementById(containerId);
  if (!wrap) return;

  const tabs = Array.from(wrap.querySelectorAll('.tool-tab'));
  const panels = tabs
    .map((b) => document.querySelector(b.dataset.target))
    .filter(Boolean);

  function activate(sel) {
    if (!sel) return;
    tabs.forEach((b) => b.classList.toggle('active', b.dataset.target === sel));
    panels.forEach((p) => p.classList.toggle('active', `#${p.id}` === sel));
    try { localStorage.setItem(storageKey, sel); } catch(e) {}
  }

  wrap.addEventListener('click', (e) => {
    const b = e.target.closest('.tool-tab');
    if (!b || !b.dataset?.target) return;
    activate(b.dataset.target);

    // Автопрокрутка, щоб активна вкладка була видима
    const rBtn = b.getBoundingClientRect();
    const rWrap = wrap.getBoundingClientRect();
    if (rBtn.left < rWrap.left) {
      wrap.scrollBy({ left: rBtn.left - rWrap.left - 8, behavior: 'smooth' });
    } else if (rBtn.right > rWrap.right) {
      wrap.scrollBy({ left: rBtn.right - rWrap.right + 8, behavior: 'smooth' });
    }
  });

  // Коліщатко миші — горизонтальний скрол
  wrap.addEventListener('wheel', (e) => {
    // якщо користувач крутить вертикально — перекидаємо у горизонт траку
    if (Math.abs(e.deltaY) > Math.abs(e.deltaX)) {
      e.preventDefault();
      wrap.scrollLeft += e.deltaY;
    }
  }, { passive: false });

  // Відновлення активної вкладки
  let saved = null;
  try { saved = localStorage.getItem(storageKey); } catch (e) {}
  const hasSaved = saved && panels.some(p => `#${p.id}` === saved);
  activate(hasSaved ? saved : (tabs[0] && tabs[0].dataset.target));
}

/* ========== Arrow buttons for horizontal tracks ========== */
function wireArrows(forId) {
  const track = document.getElementById(forId);
  const prev = document.querySelector(`.arrow-btn[data-for="${forId}"][data-arrow="prev"]`);
  const next = document.querySelector(`.arrow-btn[data-for="${forId}"][data-arrow="next"]`);
  if (!track || !prev || !next) return;

  function updateDisabled() {
    prev.disabled = track.scrollLeft <= 2;
    next.disabled = Math.ceil(track.scrollLeft + track.clientWidth) >= track.scrollWidth - 2;
  }
  updateDisabled();

  prev.addEventListener('click', () => {
    track.scrollBy({ left: -Math.round(track.clientWidth * 0.8), behavior: 'smooth' });
  });
  next.addEventListener('click', () => {
    track.scrollBy({ left:  Math.round(track.clientWidth * 0.8), behavior: 'smooth' });
  });
  track.addEventListener('scroll', updateDisabled, { passive: true });
  window.addEventListener('resize', updateDisabled);
}

/* ========== Export Modal ========== */
function initExportModal() {
  const $ = (id) => document.getElementById(id);
  const modal = $('exportModal');
  const openBtn = $('openExport');
  const closeBtn = $('closeExport');
  if (!modal || !openBtn || !closeBtn) return;

  function openModal() {
    modal.style.display = 'flex';
    document.body.style.overflow = 'hidden';
    // фокус на першій доступній кнопці експорту
    (modal.querySelector('[data-export]') || modal.querySelector('.btn'))?.focus?.();
  }
  function closeModal() {
    modal.style.display = 'none';
    document.body.style.overflow = '';
    openBtn?.focus?.();
  }

  openBtn.addEventListener('click', openModal);
  closeBtn.addEventListener('click', closeModal);
  modal.addEventListener('click', (e) => { if (e.target === modal) closeModal(); });
  window.addEventListener('keydown', (e) => { if (e.key === 'Escape' && modal.style.display === 'flex') closeModal(); });

  // Мапимо кнопки в модалці на приховані реальні кнопки експорту
  const map = {
    ascii:  'btnExportAscii',
    binary: 'btnExportBinary',
    glb:    'btnExpGLB',
    gltf:   'btnExpGLTF',
    obj:    'btnExpOBJ',
    ply:    'btnExpPLY',
  };

  modal.addEventListener('click', (e) => {
    const b = e.target.closest('[data-export]');
    if (!b) return;
    const id = map[b.getAttribute('data-export')];
    const real = id && document.getElementById(id);

    // важливо: не дати кнопці поводитись як submit у формі
    e.preventDefault();

    closeModal();
    if (!real) return;

    // дати модалці сховатись перед дією
    setTimeout(() => {
      // клік більш “натуральний”, ніж .click() у деяких браузерах
      real.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }));
    }, 60);
  });
}

/* ========================================================================== */
/*  ▼▼▼ ДОДАНО: прив’язка file input + drag&drop до viewerCtx (без зміни API) */
/* ========================================================================== */

(function bindFileLoadingAutonomously() {
  // Підключаємось, коли з'явиться window.viewerCtx або window.__STL_CTX, і контейнер #viewer.
  function getCtx() {
    // підтримка обох варіантів збереження контексту
    return (window.viewerCtx || window.__STL_CTX || null);
  }

  function attachFirstMeshIfAny(ctx) {
    if (!ctx || !ctx.modelRoot) return;
    let first = null;
    ctx.modelRoot.traverse((n) => { if (!first && n.isMesh) first = n; });
    if (first && ctx.transform?.attach) {
      ctx.transform.attach(first);
      ctx.transform.setMode?.("translate");
      ctx.transform.setSpace?.("world");
      ctx.transform.setSize?.(1);
    }
  }

  function postLoadAdjust(ctx) {
    requestAnimationFrame(() => {
      setTimeout(() => {
        if (!ctx?.modelRoot?.children?.length) return;
        // Центр/підлога
        if (typeof ctx.centerAndDropToFloor === 'function') {
          if (ctx.modelRoot.children.length === 1) {
            ctx.centerAndDropToFloor(ctx.modelRoot.children[0]);
          } else {
            ctx.centerAndDropToFloor(ctx.modelRoot);
          }
        }
        // Підігнати стіл/камеру
        ctx.resizeGridToModel?.(1.3);
        ctx.fitCameraToObject?.(ctx.modelRoot, 1.6);
        // Режим перегляду під STL
        ctx.setViewerMode?.('stl');
        // Чіпляємо ґізмо до першої меші
        attachFirstMeshIfAny(ctx);
      }, 60);
    });
  }

  function tryBind() {
    const ctx = getCtx();
    const viewer = document.getElementById('viewer');
    if (!ctx || !viewer) return false;

    // ---- FILE INPUT ----
    const fileEl =
      document.querySelector('#stlFile, #file3d, input[type="file"][data-3d], input[type="file"].stl-file') ||
      document.querySelector('input[type="file"]');

    if (fileEl && !fileEl.dataset.prooflyBound) {
      fileEl.dataset.prooflyBound = "1";
      fileEl.addEventListener('change', (e) => {
        const f = e.target.files && e.target.files[0];
        if (!f || !ctx.loadAnyFromFile) return;
        try {
          ctx.loadAnyFromFile(f);
          postLoadAdjust(ctx);
        } catch (err) {
          console.error('loadAnyFromFile failed:', err);
        }
      });
    }

    // ---- DRAG & DROP на #viewer ----
    if (!viewer.dataset.prooflyDnd) {
      viewer.dataset.prooflyDnd = "1";

      const stop = (e) => { e.preventDefault(); e.stopPropagation(); };
      ['dragenter','dragover','dragleave','drop'].forEach(ev => {
        viewer.addEventListener(ev, stop, false);
      });

      viewer.addEventListener('dragover', () => viewer.classList.add('drag-hover'));
      viewer.addEventListener('dragleave', () => viewer.classList.remove('drag-hover'));
      viewer.addEventListener('drop', (e) => {
        viewer.classList.remove('drag-hover');
        const f = e.dataTransfer?.files && e.dataTransfer.files[0];
        if (!f || !ctx.loadAnyFromFile) return;

        try {
          ctx.loadAnyFromFile(f);
          postLoadAdjust(ctx);
        } catch (err) {
          console.error('loadAnyFromFile failed:', err);
        }
      });
    }

    return true;
  }

  // Одразу і з повторними спробами (якщо ctx з'явиться пізніше)
  if (!tryBind()) {
    document.addEventListener('DOMContentLoaded', tryBind, { once: false });
    let attempts = 0;
    const t = setInterval(() => {
      if (tryBind() || ++attempts > 50) clearInterval(t);
    }, 200);
  }
})();
