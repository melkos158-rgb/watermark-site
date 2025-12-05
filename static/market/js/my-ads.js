// static/market/js/my-ads.js
console.log('my-ads.js loaded');

document.addEventListener('DOMContentLoaded', () => {
  const carousel = document.getElementById('myAdsCarousel');
  const gridInner = document.querySelector('.my-ads-grid-inner');
  const emptyMsg = document.querySelector('.my-ads-empty');
  const leftBtn = document.querySelector('.my-ads-arrow.left');
  const rightBtn = document.querySelector('.my-ads-arrow.right');

  if (!carousel || !gridInner) {
    console.warn('my-ads: DOM elements not found');
    return;
  }

  let items = [];
  let currentIndex = 0;

  function renderEmpty() {
    if (emptyMsg) emptyMsg.style.display = 'block';
    carousel.innerHTML = '';
    gridInner.innerHTML = '';
  }

  function createCard(item, isLarge = false) {
    const card = document.createElement('article');
    card.className = 'my-ads-card';
    if (isLarge) card.classList.add('my-ads-card-large');

    const thumb = document.createElement('img');
    thumb.className = 'my-ads-card-thumb';
    thumb.src = item.cover_url || item.cover || '/static/img/placeholder_stl.jpg';
    thumb.alt = item.title || '3D модель';

    const body = document.createElement('div');
    body.className = 'my-ads-card-body';

    const title = document.createElement('div');
    title.className = 'my-ads-card-title';
    title.textContent = item.title || 'Без назви';

    const meta = document.createElement('div');
    meta.className = 'my-ads-card-meta';
    const rawPrice = Number(item.price || 0);
    const priceText = !rawPrice ? 'Безкоштовно' : `${rawPrice.toFixed(2)} zł`;
    meta.textContent = priceText;

    const actions = document.createElement('div');
    actions.className = 'my-ads-card-actions';

    const viewLink = document.createElement('a');
    viewLink.href = `/item/${item.id}`;
    viewLink.className = 'btn btn-sm btn-secondary';
    viewLink.textContent = 'Дивитися';

    const editLink = document.createElement('a');
    editLink.href = `/edit/${item.id}`;
    editLink.className = 'btn btn-sm btn-outline-secondary';
    editLink.textContent = 'Редагувати';

    actions.appendChild(viewLink);
    actions.appendChild(editLink);

    body.appendChild(title);
    body.appendChild(meta);
    body.appendChild(actions);

    card.appendChild(thumb);
    card.appendChild(body);

    return card;
  }

  function renderCarousel() {
    carousel.innerHTML = '';
    if (!items.length) {
      renderEmpty();
      return;
    }
    if (emptyMsg) emptyMsg.style.display = 'none';

    const center = createCard(items[currentIndex], true);
    carousel.appendChild(center);
  }

  function renderGrid() {
    gridInner.innerHTML = '';
    if (!items.length) return;
    items.forEach((it) => {
      gridInner.appendChild(createCard(it, false));
    });
  }

  function shift(delta) {
    if (!items.length) return;
    currentIndex = (currentIndex + delta + items.length) % items.length;
    renderCarousel();
  }

  if (leftBtn) leftBtn.addEventListener('click', () => shift(-1));
  if (rightBtn) rightBtn.addEventListener('click', () => shift(1));

  function loadMyItems() {
    console.log('my-ads: fetching /api/my/items?page=1');
    fetch('/api/my/items?page=1', { credentials: 'same-origin' })
      .then((r) => {
        console.log('my-ads: status', r.status);
        if (!r.ok) throw new Error('status ' + r.status);
        return r.json();
      })
      .then((data) => {
        console.log('my-ads: json', data);
        items = (data && data.items) || [];
        if (!items.length) {
          renderEmpty();
          return;
        }
        renderCarousel();
        renderGrid();
      })
      .catch((err) => {
        console.error('my-ads fetch error', err);
        renderEmpty();
      });
  }

  loadMyItems();
});
