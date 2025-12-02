/**
 * My Ads Carousel - Progressive Enhancement
 * Manages the carousel behavior for the My Ads page
 */

(function() {
  'use strict';

  // Wait for DOM to be ready
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

  function init() {
    const carousel = document.getElementById('my-carousel');
    if (!carousel) return;

    const itemsCount = parseInt(carousel.dataset.itemsCount || '0', 10);
    if (itemsCount === 0) return;

    // Get all carousel items (server-rendered, hidden)
    const carouselItems = Array.from(document.querySelectorAll('.mc-carousel-item'));
    if (carouselItems.length === 0) return;

    // Get display cards
    const leftCard = document.getElementById('mc-left-card');
    const mainCard = document.getElementById('mc-main-card');
    const rightCard = document.getElementById('mc-right-card');
    const editBtn = document.getElementById('mc-edit-btn');

    // Get arrow buttons
    const prevBtn = carousel.querySelector('[data-dir="prev"]');
    const nextBtn = carousel.querySelector('[data-dir="next"]');

    let currentIndex = 0;

    /**
     * Get the item data for a given index
     */
    function getItemData(index) {
      if (index < 0 || index >= carouselItems.length) return null;
      const item = carouselItems[index];
      return {
        id: item.dataset.itemId,
        thumb: item.querySelector('.mc-item-thumb')?.src || '',
        title: item.querySelector('.mc-item-title')?.textContent || '',
        price: item.querySelector('.mc-item-price')?.textContent || '',
        editUrl: item.querySelector('.mc-item-edit')?.href || '#'
      };
    }

    /**
     * Update a display card with item data
     */
    function updateCard(card, data) {
      if (!card || !data) return;
      const thumb = card.querySelector('[data-role="thumb"]');
      const title = card.querySelector('[data-role="title"]');
      
      if (thumb) {
        thumb.style.backgroundImage = data.thumb ? `url('${data.thumb}')` : '';
      }
      if (title) {
        title.textContent = data.title;
      }
    }

    /**
     * Render the carousel at the current index
     */
    function render() {
      const prevIndex = (currentIndex - 1 + carouselItems.length) % carouselItems.length;
      const nextIndex = (currentIndex + 1) % carouselItems.length;

      const prevData = getItemData(prevIndex);
      const currData = getItemData(currentIndex);
      const nextData = getItemData(nextIndex);

      // Update cards
      if (carouselItems.length >= 3) {
        updateCard(leftCard, prevData);
        updateCard(rightCard, nextData);
        if (leftCard) leftCard.style.display = 'flex';
        if (rightCard) rightCard.style.display = 'flex';
      } else if (carouselItems.length === 2) {
        updateCard(leftCard, prevData);
        if (leftCard) leftCard.style.display = 'flex';
        if (rightCard) rightCard.style.display = 'none';
      } else {
        if (leftCard) leftCard.style.display = 'none';
        if (rightCard) rightCard.style.display = 'none';
      }

      updateCard(mainCard, currData);
      
      if (editBtn && currData) {
        editBtn.href = currData.editUrl;
      }

      // Update button states
      if (carouselItems.length <= 1) {
        if (prevBtn) prevBtn.disabled = true;
        if (nextBtn) nextBtn.disabled = true;
      } else {
        if (prevBtn) prevBtn.disabled = false;
        if (nextBtn) nextBtn.disabled = false;
      }
    }

    /**
     * Navigate to previous item
     */
    function goToPrev() {
      currentIndex = (currentIndex - 1 + carouselItems.length) % carouselItems.length;
      render();
    }

    /**
     * Navigate to next item
     */
    function goToNext() {
      currentIndex = (currentIndex + 1) % carouselItems.length;
      render();
    }

    // Event listeners for arrow buttons
    if (prevBtn) {
      prevBtn.addEventListener('click', goToPrev);
    }
    if (nextBtn) {
      nextBtn.addEventListener('click', goToNext);
    }

    // Keyboard navigation
    document.addEventListener('keydown', function(e) {
      // Only handle keyboard if carousel is visible
      if (!carousel.offsetParent) return;
      
      if (e.key === 'ArrowLeft' || e.key === 'Left') {
        e.preventDefault();
        goToPrev();
      } else if (e.key === 'ArrowRight' || e.key === 'Right') {
        e.preventDefault();
        goToNext();
      }
    });

    // Touch/swipe support (basic)
    let touchStartX = 0;
    let touchEndX = 0;

    carousel.addEventListener('touchstart', function(e) {
      touchStartX = e.changedTouches[0].screenX;
    }, { passive: true });

    carousel.addEventListener('touchend', function(e) {
      touchEndX = e.changedTouches[0].screenX;
      handleSwipe();
    }, { passive: true });

    function handleSwipe() {
      const swipeThreshold = 50;
      if (touchEndX < touchStartX - swipeThreshold) {
        goToNext();
      } else if (touchEndX > touchStartX + swipeThreshold) {
        goToPrev();
      }
    }

    // Initial render
    render();

    // Auto-rotate (optional, disabled by default)
    // Uncomment to enable auto-rotation every 5 seconds
    /*
    let autoRotateInterval = setInterval(goToNext, 5000);
    
    // Pause auto-rotate on hover
    carousel.addEventListener('mouseenter', function() {
      clearInterval(autoRotateInterval);
    });
    
    carousel.addEventListener('mouseleave', function() {
      autoRotateInterval = setInterval(goToNext, 5000);
    });
    */
  }
})();
