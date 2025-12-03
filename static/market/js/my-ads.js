// Simple carousel behavior for my-ads page.
// Progressive enhancement: server renders initial order; JS attaches handlers.
document.addEventListener('DOMContentLoaded', function(){
  const carousel = document.getElementById('myAdsCarousel');
  if (!carousel) return;

  const gridInner = document.querySelector('.my-ads-grid-inner');
  const emptyMessage = document.querySelector('.my-ads-empty');

  // Function to validate and sanitize URL for CSS background-image
  function sanitizeImageUrl(url) {
    if (!url) return '/static/img/placeholder_stl.jpg';
    
    // Only allow safe URLs (http/https, data URIs, or relative paths)
    try {
      // Handle relative paths
      if (url.startsWith('/')) {
        return url;
      }
      // Handle data URIs
      if (url.startsWith('data:image/')) {
        return url;
      }
      // Handle absolute URLs - validate they're http/https
      const parsed = new URL(url, window.location.origin);
      if (parsed.protocol === 'http:' || parsed.protocol === 'https:') {
        return parsed.href;
      }
    } catch (e) {
      // Invalid URL, use placeholder
      return '/static/img/placeholder_stl.jpg';
    }
    
    // If we can't validate it safely, use placeholder
    return '/static/img/placeholder_stl.jpg';
  }

  // Function to get thumbnail URL with fallback
  function getThumbUrl(item) {
    const url = item.cover_url || item.cover || item.thumbnail || item.thumb || item.image || '/static/img/placeholder_stl.jpg';
    return sanitizeImageUrl(url);
  }

  // Function to create carousel item DOM
  function createCarouselItem(item, index) {
    const div = document.createElement('div');
    div.className = 'carousel-item';
    div.setAttribute('data-index', index);
    div.setAttribute('data-ad-id', item.id);
    
    const thumbUrl = getThumbUrl(item);
    const titleText = item.title || '';
    
    // Create elements safely without innerHTML
    const thumbDiv = document.createElement('div');
    thumbDiv.className = 'carousel-thumb';
    thumbDiv.style.backgroundImage = `url('${thumbUrl}')`;
    
    const metaDiv = document.createElement('div');
    metaDiv.className = 'carousel-meta';
    
    const titleDiv = document.createElement('div');
    titleDiv.className = 'carousel-title';
    titleDiv.textContent = titleText;
    metaDiv.appendChild(titleDiv);
    
    if (item.price !== undefined) {
      const priceDiv = document.createElement('div');
      priceDiv.className = 'carousel-price';
      priceDiv.textContent = item.price;
      metaDiv.appendChild(priceDiv);
    }
    
    div.appendChild(thumbDiv);
    div.appendChild(metaDiv);
    return div;
  }

  // Function to create grid item DOM
  function createGridItem(item) {
    const article = document.createElement('article');
    article.className = 'ad-card';
    article.setAttribute('data-ad-id', item.id);
    
    const thumbUrl = getThumbUrl(item);
    const titleText = item.title || '';
    
    // Create elements safely
    const thumbDiv = document.createElement('div');
    thumbDiv.className = 'ad-thumb';
    thumbDiv.setAttribute('role', 'img');
    thumbDiv.setAttribute('aria-label', `Мініатюра ${titleText}`);
    thumbDiv.style.backgroundImage = `url('${thumbUrl}')`;
    
    const infoDiv = document.createElement('div');
    infoDiv.className = 'ad-info';
    
    const titleDiv = document.createElement('div');
    titleDiv.className = 'ad-title';
    titleDiv.textContent = titleText;
    
    const priceDiv = document.createElement('div');
    priceDiv.className = 'ad-price';
    priceDiv.textContent = item.price !== undefined ? item.price : '';
    
    infoDiv.appendChild(titleDiv);
    infoDiv.appendChild(priceDiv);
    
    const editLink = document.createElement('a');
    editLink.className = 'ad-edit';
    editLink.href = `/edit/${item.id}`;
    editLink.textContent = 'Редагувати';
    
    article.appendChild(thumbDiv);
    article.appendChild(infoDiv);
    article.appendChild(editLink);
    
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

  // Store event handlers to properly remove them
  let carouselHandlers = null;

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

    function handleKeydown(e) {
      if (e.key === 'ArrowLeft') rotateLeft();
      if (e.key === 'ArrowRight') rotateRight();
    }

    // Remove previous event listeners if they exist
    if (carouselHandlers) {
      if (leftBtn && carouselHandlers.rotateLeft) {
        leftBtn.removeEventListener('click', carouselHandlers.rotateLeft);
      }
      if (rightBtn && carouselHandlers.rotateRight) {
        rightBtn.removeEventListener('click', carouselHandlers.rotateRight);
      }
      if (carouselHandlers.handleKeydown) {
        carousel.removeEventListener('keydown', carouselHandlers.handleKeydown);
      }
    }

    // Store handlers for future cleanup
    carouselHandlers = {
      rotateLeft: rotateLeft,
      rotateRight: rotateRight,
      handleKeydown: handleKeydown
    };

    // Add new event listeners
    if (leftBtn) {
      leftBtn.addEventListener('click', rotateLeft);
    }
    if (rightBtn) {
      rightBtn.addEventListener('click', rotateRight);
    }

    // Keyboard navigation
    carousel.setAttribute('tabindex', '0');
    carousel.addEventListener('keydown', handleKeydown);
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
