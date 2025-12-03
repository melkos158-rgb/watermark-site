// my-ads.js — завантаження даних та інтеграція з каруселлю
document.addEventListener('DOMContentLoaded', function(){
  const carousel = document.getElementById('myAdsCarousel');
  const gridInner = document.querySelector('.my-ads-grid-inner');
  const emptyMsg = document.querySelector('.my-ads-empty');
  const leftBtn = document.querySelector('.my-ads-arrow.left');
  const rightBtn = document.querySelector('.my-ads-arrow.right');

  function clearContainers() {
    if (carousel) carousel.innerHTML = '';
    if (gridInner) gridInner.innerHTML = '';
  }

  function showEmpty(show) {
    if (!emptyMsg) return;
    emptyMsg.style.display = show ? '' : 'none';
    if (carousel) carousel.style.display = show ? 'none' : '';
    if (gridInner) gridInner.style.display = show ? 'none' : '';
    if (leftBtn) leftBtn.style.display = show ? 'none' : '';
    if (rightBtn) rightBtn.style.display = show ? 'none' : '';
  }

  function createCarouselItem(item, idx) {
    const div = document.createElement('div');
    div.className = 'carousel-item';
    div.dataset.index = idx;
    div.dataset.adId = item.id;

    const thumb = document.createElement('div');
    thumb.className = 'carousel-thumb';
    const thumbUrl = item.thumbnail || item.thumb || item.image || item.cover_url || '/static/img/placeholder_stl.jpg';
    thumb.style.backgroundImage = `url('${thumbUrl}')`;

    const meta = document.createElement('div');
    meta.className = 'carousel-meta';
    const title = document.createElement('div');
    title.className = 'carousel-title';
    title.textContent = item.title || '';
    const price = document.createElement('div');
    price.className = 'carousel-price';
    price.textContent = (item.price !== undefined && item.price !== null) ? item.price : '';

    meta.appendChild(title);
    meta.appendChild(price);

    div.appendChild(thumb);
    div.appendChild(meta);

    return div;
  }

  function createGridItem(item) {
    const article = document.createElement('article');
    article.className = 'ad-card';
    article.dataset.adId = item.id;

    const thumb = document.createElement('div');
    thumb.className = 'ad-thumb';
    const thumbUrl = item.thumbnail || item.thumb || item.image || item.cover_url || '/static/img/placeholder_stl.jpg';
    thumb.style.backgroundImage = `url('${thumbUrl}')`;
    thumb.setAttribute('role','img');
    thumb.setAttribute('aria-label', `Мініатюра ${item.title || ''}`);

    const info = document.createElement('div');
    info.className = 'ad-info';
    const t = document.createElement('div');
    t.className = 'ad-title';
    t.textContent = item.title || '';
    const p = document.createElement('div');
    p.className = 'ad-price';
    p.textContent = (item.price !== undefined && item.price !== null) ? item.price : '';

    info.appendChild(t);
    info.appendChild(p);

    const edit = document.createElement('a');
    edit.className = 'ad-edit';
    edit.href = `/ads/${item.id}/edit`;
    edit.textContent = 'Редагувати';

    article.appendChild(thumb);
    article.appendChild(info);
    article.appendChild(edit);

    return article;
  }

  function injectItems(items) {
    clearContainers();
    if (!items || items.length === 0) {
      showEmpty(true);
      return;
    }
    showEmpty(false);

    // Carousel: append all items
    items.forEach((it, idx) => {
      const cItem = createCarouselItem(it, idx);
      if (carousel) carousel.appendChild(cItem);
    });

    // Grid: limit to 8 items like design (4x2)
    const gridItems = items.slice(0, 8);
    gridItems.forEach(it => {
      const gItem = createGridItem(it);
      if (gridInner) gridInner.appendChild(gItem);
    });

    // Notify other code that items injected
    document.dispatchEvent(new Event('myAds:itemsInjected'));
  }

  function loadMyItems() {
    fetch('/api/my/items?page=1', { credentials: 'same-origin' })
      .then(resp => {
        if (!resp.ok) throw new Error('Network response was not ok');
        return resp.json();
      })
      .then(json => {
        let items = [];
        if (Array.isArray(json)) items = json;
        else if (json.items && Array.isArray(json.items)) items = json.items;
        else if (json.data && json.data.items && Array.isArray(json.data.items)) items = json.data.items;
        else if (json.data && Array.isArray(json.data)) items = json.data;
        else if (json.results && Array.isArray(json.results)) items = json.results;
        injectItems(items);
      })
      .catch(err => {
        console.error('Failed to load my items:', err);
        showEmpty(true);
      });
  }

  loadMyItems();

  document.addEventListener('myAds:itemsInjected', function(){
    const items = carousel ? Array.from(carousel.querySelectorAll('.carousel-item')) : [];
    items.forEach((it, idx) => {
      it.addEventListener('click', () => {
        items.forEach(i => i.classList.remove('active','prev','next'));
        it.classList.add('active');
        const prevIdx = (idx - 1 + items.length) % items.length;
        const nextIdx = (idx + 1) % items.length;
        if (items[prevIdx]) items[prevIdx].classList.add('prev');
        if (items[nextIdx]) items[nextIdx].classList.add('next');
      });
    });
  });
});
