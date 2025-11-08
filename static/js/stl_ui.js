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
