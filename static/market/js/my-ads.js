// Simple carousel behavior for my-ads page.
// Progressive enhancement: server renders initial order; JS attaches handlers.
document.addEventListener('DOMContentLoaded', function(){
  const carousel = document.getElementById('myAdsCarousel');
  if (!carousel) return;

  const gridInner = document.querySelector('.my-ads-grid-inner');
  const emptyMessage = document.querySelector('.my-ads-empty');

  // Function to get thumbnail URL with fallback
  function getThumbUrl(item) {
    return item.cover_url || item.cover || item.thumbnail || item.thumb || item.image || '/static/img/placeholder_stl.jpg';
  }

  // Function to create carousel item DOM
  function createCarouselItem(item, index) {
    const div = document.createElement('div');
    div.className = 'carousel-item';
    div.setAttribute('data-index', index);
    div.setAttribute('data-ad-id', item.id);
    
    const thumbUrl = getThumbUrl(item);
    div.innerHTML = `
      <div class="carousel-thumb" style="background-image: url('${thumbUrl}')"></div>
      <div class="carousel-meta">
        <div class="carousel-title">${item.title || ''}</div>
        ${item.price !== undefined ? `<div class="carousel-price">${item.price}</div>` : ''}
      </div>
    `;
    return div;
  }

  // Function to create grid item DOM
  function createGridItem(item) {
    const article = document.createElement('article');
    article.className = 'ad-card';
    article.setAttribute('data-ad-id', item.id);
    
    const thumbUrl = getThumbUrl(item);
    article.innerHTML = `
      <div class="ad-thumb" role="img" aria-label="Мініатюра ${item.title || ''}" style="background-image: url('${thumbUrl}')"></div>
      <div class="ad-info">
        <div class="ad-title">${item.title || ''}</div>
        <div class="ad-price">${item.price !== undefined ? item.price : ''}</div>
      </div>
      <a class="ad-edit" href="/edit/${item.id}">Редагувати</a>
    `;
    return article;
  }

  // Function to render items
  function renderItems(items) {
    if (!items || items.length === 0) {
      // Show empty message
      if (emptyMessage) {
        emptyMessage.style.display = 'block';
      }
      return;
    }

    // Hide empty message if items exist
    if (emptyMessage) {
      emptyMessage.style.display = 'none';
    }

    // Clear existing content (if fetching from API)
    carousel.innerHTML = '';
    if (gridInner) gridInner.innerHTML = '';

    // Create carousel items
    items.forEach((item, index) => {
      const carouselItem = createCarouselItem(item, index);
      carousel.appendChild(carouselItem);
      
      // Create grid item
      if (gridInner) {
        const gridItem = createGridItem(item);
        gridInner.appendChild(gridItem);
      }
    });

    // Initialize carousel behavior after items are added
    initCarousel();
  }

  // Function to initialize carousel behavior
  function initCarousel() {
    const items = Array.from(carousel.querySelectorAll('.carousel-item'));
    if (items.length === 0) return;

    let activeIndex = 0;

    // If >=3 items, set center to index 1 initially to match mockup
    if (items.length >= 3) activeIndex = 1;

    function applyState() {
      items.forEach((it, idx) => {
        it.classList.remove('active','prev','next');
        if (idx === activeIndex) it.classList.add('active');
        else if (idx === (activeIndex - 1 + items.length) % items.length) it.classList.add('prev');
        else if (idx === (activeIndex + 1) % items.length) it.classList.add('next');
      });
    }

    applyState();

    const leftBtn = document.querySelector('.my-ads-arrow.left');
    const rightBtn = document.querySelector('.my-ads-arrow.right');

    function rotateLeft(){
      activeIndex = (activeIndex - 1 + items.length) % items.length;
      applyState();
      items[activeIndex].scrollIntoView({inline:'center', behavior:'smooth'});
    }
    function rotateRight(){
      activeIndex = (activeIndex + 1) % items.length;
      applyState();
      items[activeIndex].scrollIntoView({inline:'center', behavior:'smooth'});
    }

    if (leftBtn) {
      leftBtn.removeEventListener('click', rotateLeft);
      leftBtn.addEventListener('click', rotateLeft);
    }
    if (rightBtn) {
      rightBtn.removeEventListener('click', rotateRight);
      rightBtn.addEventListener('click', rotateRight);
    }

    // Keyboard navigation
    carousel.setAttribute('tabindex', '0');
    carousel.removeEventListener('keydown', handleKeydown);
    carousel.addEventListener('keydown', handleKeydown);

    function handleKeydown(e) {
      if (e.key === 'ArrowLeft') rotateLeft();
      if (e.key === 'ArrowRight') rotateRight();
    }
  }

  // Check if items are already server-rendered
  const existingItems = carousel.querySelectorAll('.carousel-item');
  if (existingItems.length > 0) {
    // Progressive enhancement: items already exist, just initialize carousel
    initCarousel();
  } else {
    // Fetch items from API
    fetch('/api/my/items?page=1')
      .then(response => {
        if (!response.ok) {
          throw new Error('Network response was not ok');
        }
        return response.json();
      })
      .then(data => {
        // Handle both common response shapes: data.items or items
        const items = data.items || data || [];
        renderItems(items);
      })
      .catch(error => {
        console.error('Error fetching items:', error);
        // Show empty message on error
        if (emptyMessage) {
          emptyMessage.style.display = 'block';
        }
      });
  }
});
