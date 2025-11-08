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
    tabs.forEach((b) => b.classList.toggle('active', b.dataset.target === sel));
    panels.forEach((p) => p.classList.toggle('active', `#${p.id}` === sel));
    try { localStorage.setItem(storageKey, sel); } catch(e) {}
  }

  wrap.addEventListener('click', (e) => {
    const b = e.target.closest('.tool-tab');
    if (!b) return;
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
    if (Math.abs(e.deltaY) > Math.abs(e.deltaX)) {
      e.preventDefault();
      wrap.scrollLeft += e.deltaY;
    }
  }, { passive: false });

  const saved = localStorage.getItem(storageKey);
  activate(saved || (tabs[0] && tabs[0].dataset.target));
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
    modal.querySelector('.btn')?.focus();
  }
  function closeModal() {
    modal.style.display = 'none';
    document.body.style.overflow = '';
    openBtn.focus();
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
    const real = document.getElementById(id);
    closeModal();
    setTimeout(() => real?.click(), 60); // дати модалці сховатись перед дією
  });
}

/* ========================================================================== */
/*  ▼▼▼ ДОДАНО: прив’язка file input + drag&drop до viewerCtx (без зміни API) */
/* ========================================================================== */

(function bindFileLoadingAutonomously() {
  // Підключаємось, коли з'явиться window.viewerCtx і контейнер #viewer.
  function tryBind() {
    const ctx = window.viewerCtx;
    const viewer = document.getElementById('viewer');
    if (!ctx || !viewer) return false;

    // ---- FILE INPUT ----
    const fileEl =
      document.querySelector('#stlFile, #file3d, input[type="file"][data-3d], input[type="file"].stl-file') ||
      document.querySelector('input[type="file"]');

    if (fileEl && !fileEl.__prooflyBound) {
      fileEl.__prooflyBound = true;
      fileEl.addEventListener('change', (e) => {
        const f = e.target.files && e.target.files[0];
        if (!f || !ctx.loadAnyFromFile) return;

        try { ctx.loadAnyFromFile(f); } catch (err) {
          console.error('loadAnyFromFile failed:', err);
          return;
        }

        // М'яко підлаштувати сцену після того, як лоадер додасть модель.
        requestAnimationFrame(() => {
          setTimeout(() => {
            if (ctx.modelRoot?.children?.length) {
              // Центруємо та садимо на стіл (стандарт для STL-режиму)
              if (typeof ctx.centerAndDropToFloor === 'function') {
                // якщо всередині один об'єкт — центруємо його
                if (ctx.modelRoot.children.length === 1) {
                  ctx.centerAndDropToFloor(ctx.modelRoot.children[0]);
                } else {
                  ctx.centerAndDropToFloor(ctx.modelRoot);
                }
              }
              if (typeof ctx.fitCameraToObject === 'function') {
                ctx.fitCameraToObject(ctx.modelRoot, 1.6);
              }
              if (typeof ctx.setViewerMode === 'function') {
                ctx.setViewerMode('stl'); // показує стіл, вимикає авто-спін
              }
            }
          }, 60);
        });
      });
    }

    // ---- DRAG & DROP на #viewer ----
    if (!viewer.__prooflyDnd) {
      viewer.__prooflyDnd = true;

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

        try { ctx.loadAnyFromFile(f); } catch (err) {
          console.error('loadAnyFromFile failed:', err);
          return;
        }

        requestAnimationFrame(() => {
          setTimeout(() => {
            if (ctx.modelRoot?.children?.length) {
              if (typeof ctx.centerAndDropToFloor === 'function') {
                if (ctx.modelRoot.children.length === 1) {
                  ctx.centerAndDropToFloor(ctx.modelRoot.children[0]);
                } else {
                  ctx.centerAndDropToFloor(ctx.modelRoot);
                }
              }
              if (typeof ctx.fitCameraToObject === 'function') {
                ctx.fitCameraToObject(ctx.modelRoot, 1.6);
              }
              if (typeof ctx.setViewerMode === 'function') {
                ctx.setViewerMode('stl');
              }
            }
          }, 60);
        });
      });
    }

    return true;
  }

  // Пробуємо одразу, потім ще кілька разів із інтервалом (на випадок, якщо ctx ще не готовий)
  if (!tryBind()) {
    document.addEventListener('DOMContentLoaded', tryBind, { once: false });
    let attempts = 0;
    const t = setInterval(() => {
      if (tryBind() || ++attempts > 50) clearInterval(t);
    }, 200);
  }
})();
