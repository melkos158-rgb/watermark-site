// My Ads - Carousel functionality
// Progressive enhancement: server renders initial state, JS adds interactivity

(function() {
  'use strict';

  // Get ads data from global variable
  const adsData = window.MY_ADS_DATA || [];
  
  if (!adsData || adsData.length === 0) {
    // No ads, nothing to do
    return;
  }

  // DOM elements
  const carousel = document.getElementById('my-ads-carousel');
  if (!carousel) return;

  const prevCard = carousel.querySelector('[data-position="prev"]');
  const currentCard = carousel.querySelector('[data-position="current"]');
  const nextCard = carousel.querySelector('[data-position="next"]');
  const prevBtn = carousel.querySelector('.my-ads-arrow-left');
  const nextBtn = carousel.querySelector('.my-ads-arrow-right');

  if (!prevCard || !currentCard || !nextCard || !prevBtn || !nextBtn) {
    console.warn('[my-ads] Missing carousel elements');
    return;
  }

  // State
  let currentIndex = 0;

  // Helper: Get prev/next index with wrap-around
  function getPrevIndex(index) {
    return index === 0 ? adsData.length - 1 : index - 1;
  }

  function getNextIndex(index) {
    return index === adsData.length - 1 ? 0 : index + 1;
  }

  // Helper: Format price
  function formatPrice(ad) {
    if (!ad.price || ad.price === 0) {
      return 'Безкоштовно';
    }
    return ad.price + ' PLN';
  }

  // Helper: Get thumbnail URL
  function getThumbnail(ad) {
    return ad.thumbnail || ad.cover || ad.cover_url || '/static/img/placeholder_stl.jpg';
  }

  // Update carousel display
  function updateCarousel() {
    const currentAd = adsData[currentIndex];
    const prevAd = adsData[getPrevIndex(currentIndex)];
    const nextAd = adsData[getNextIndex(currentIndex)];

    // Update current (main) card
    const currentThumb = currentCard.querySelector('.my-ads-card-thumb');
    const currentOverlay = currentCard.querySelector('.my-ads-card-overlay');
    
    if (currentThumb) {
      currentThumb.style.backgroundImage = `url('${getThumbnail(currentAd)}')`;
    }
    
    if (currentOverlay) {
      const titleEl = currentOverlay.querySelector('.my-ads-card-title');
      const priceEl = currentOverlay.querySelector('.my-ads-card-price');
      
      if (titleEl) titleEl.textContent = currentAd.title || 'Без назви';
      if (priceEl) priceEl.textContent = formatPrice(currentAd);
    }

    // Update preview cards (only if we have more than 1 ad)
    if (adsData.length > 1) {
      // Previous card
      const prevThumb = prevCard.querySelector('.my-ads-card-thumb');
      if (prevThumb) {
        prevThumb.style.backgroundImage = `url('${getThumbnail(prevAd)}')`;
      }
      prevCard.style.display = '';

      // Next card
      const nextThumb = nextCard.querySelector('.my-ads-card-thumb');
      if (nextThumb) {
        nextThumb.style.backgroundImage = `url('${getThumbnail(nextAd)}')`;
      }
      nextCard.style.display = '';
    } else {
      // Hide preview cards if only 1 ad
      prevCard.style.display = 'none';
      nextCard.style.display = 'none';
    }

    // Update button states (disable if only 1 ad)
    if (adsData.length <= 1) {
      prevBtn.disabled = true;
      nextBtn.disabled = true;
    } else {
      prevBtn.disabled = false;
      nextBtn.disabled = false;
    }

    // Highlight current ad in grid
    highlightGridCard(currentAd.id);
  }

  // Highlight the corresponding card in the grid
  function highlightGridCard(adId) {
    const gridCards = document.querySelectorAll('.my-ads-grid-card');
    gridCards.forEach(card => {
      const cardId = parseInt(card.dataset.adId, 10);
      if (cardId === parseInt(adId, 10)) {
        card.classList.add('my-ads-grid-card-highlighted');
      } else {
        card.classList.remove('my-ads-grid-card-highlighted');
      }
    });
  }

  // Navigation handlers
  function goToPrev() {
    currentIndex = getPrevIndex(currentIndex);
    updateCarousel();
  }

  function goToNext() {
    currentIndex = getNextIndex(currentIndex);
    updateCarousel();
  }

  // Event listeners
  prevBtn.addEventListener('click', goToPrev);
  nextBtn.addEventListener('click', goToNext);

  // Keyboard navigation
  document.addEventListener('keydown', function(e) {
    // Only if carousel is in viewport
    const rect = carousel.getBoundingClientRect();
    const inViewport = rect.top < window.innerHeight && rect.bottom > 0;
    
    if (!inViewport) return;

    if (e.key === 'ArrowLeft') {
      e.preventDefault();
      goToPrev();
    } else if (e.key === 'ArrowRight') {
      e.preventDefault();
      goToNext();
    }
  });

  // Allow clicking grid cards to update carousel
  const gridCards = document.querySelectorAll('.my-ads-grid-card');
  gridCards.forEach(card => {
    // Set background image from data attribute
    const thumb = card.querySelector('.my-ads-grid-card-thumb');
    const thumbnailUrl = card.dataset.thumbnail;
    if (thumb && thumbnailUrl) {
      thumb.style.backgroundImage = `url('${thumbnailUrl}')`;
    }
    
    card.addEventListener('click', function(e) {
      // Don't intercept edit button clicks
      if (e.target.classList.contains('my-ads-grid-card-edit-btn')) {
        return;
      }
      
      const adId = parseInt(card.dataset.adId, 10);
      const index = adsData.findIndex(ad => ad.id === adId);
      
      if (index !== -1) {
        currentIndex = index;
        updateCarousel();
        
        // Scroll to carousel
        carousel.scrollIntoView({ behavior: 'smooth', block: 'center' });
      }
    });
  });

  // Initialize carousel on page load
  updateCarousel();

  // Optional: Auto-rotate carousel (uncomment if desired)
  // let autoRotateInterval = null;
  // function startAutoRotate() {
  //   autoRotateInterval = setInterval(goToNext, 5000);
  // }
  // function stopAutoRotate() {
  //   if (autoRotateInterval) {
  //     clearInterval(autoRotateInterval);
  //     autoRotateInterval = null;
  //   }
  // }
  // startAutoRotate();
  // carousel.addEventListener('mouseenter', stopAutoRotate);
  // carousel.addEventListener('mouseleave', startAutoRotate);

})();
