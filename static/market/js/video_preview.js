/**
 * 🎬 VIDEO PREVIEW HANDLER
 * 
 * Handles hover-to-play video preview on market cards (like Cults)
 * 
 * Features:
 * - Desktop: hover → autoplay
 * - Mobile: tap → toggle play
 * - Lazy load: preload="none" until hover
 * - Performance: pause + reset on leave
 */

(function() {
  'use strict';

  const IS_MOBILE = /Android|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i.test(navigator.userAgent);
  const IS_TOUCH = 'ontouchstart' in window || navigator.maxTouchPoints > 0;

  /**
   * Initialize video preview on all cards
   */
  function initVideoPreview() {
    const cards = document.querySelectorAll('.card-preview');
    
    cards.forEach(card => {
      const video = card.querySelector('.card-video');
      if (!video) return;

      // Mark card as having video
      card.setAttribute('data-has-video', 'true');

      if (IS_MOBILE || IS_TOUCH) {
        // Mobile/touch: tap to toggle
        setupTouchPreview(card, video);
      } else {
        // Desktop: hover to play
        setupHoverPreview(card, video);
      }
    });

    console.log(`[VIDEO] Initialized ${cards.length} video previews`);
  }

  /**
   * Setup hover-based preview (desktop)
   */
  function setupHoverPreview(card, video) {
    let hoverTimeout = null;

    card.addEventListener('mouseenter', () => {
      // Delay autoplay by 300ms (prevent accidental triggers)
      hoverTimeout = setTimeout(() => {
        video.style.display = 'block';
        video.play().catch(err => {
          console.warn('[VIDEO] Autoplay failed:', err);
        });
      }, 300);
    });

    card.addEventListener('mouseleave', () => {
      // Cancel delayed play
      if (hoverTimeout) {
        clearTimeout(hoverTimeout);
        hoverTimeout = null;
      }

      // Pause and reset
      video.pause();
      video.currentTime = 0;
      video.style.display = 'none';
    });
  }

  /**
   * Setup tap-based preview (mobile/touch)
   */
  function setupTouchPreview(card, video) {
    let isPlaying = false;

    card.addEventListener('click', (e) => {
      // Don't interfere with link clicks
      if (e.target.closest('a')) return;

      e.preventDefault();
      e.stopPropagation();

      isPlaying = !isPlaying;
      card.setAttribute('data-video-active', isPlaying ? 'true' : 'false');

      if (isPlaying) {
        video.style.display = 'block';
        video.play().catch(err => {
          console.warn('[VIDEO] Play failed:', err);
          isPlaying = false;
          card.setAttribute('data-video-active', 'false');
        });
      } else {
        video.pause();
        video.currentTime = 0;
        video.style.display = 'none';
      }
    });

    // Auto-pause when scrolling away (performance)
    const observer = new IntersectionObserver((entries) => {
      entries.forEach(entry => {
        if (!entry.isIntersecting && isPlaying) {
          video.pause();
          video.currentTime = 0;
          video.style.display = 'none';
          isPlaying = false;
          card.setAttribute('data-video-active', 'false');
        }
      });
    }, { threshold: 0.5 });

    observer.observe(card);
  }

  /**
   * Lazy load videos on scroll (optional optimization)
   */
  function lazyLoadVideos() {
    const videos = document.querySelectorAll('.card-video[preload="none"]');
    
    const observer = new IntersectionObserver((entries) => {
      entries.forEach(entry => {
        if (entry.isIntersecting) {
          const video = entry.target;
          
          // Preload metadata only (not full video)
          video.preload = 'metadata';
          
          // Mark as loading
          video.setAttribute('data-loading', 'true');
          
          video.addEventListener('loadedmetadata', () => {
            video.removeAttribute('data-loading');
          }, { once: true });

          observer.unobserve(video);
        }
      });
    }, {
      rootMargin: '200px' // Start loading before visible
    });

    videos.forEach(video => observer.observe(video));
  }

  /**
   * Auto-initialize on DOM ready
   */
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
      initVideoPreview();
      lazyLoadVideos();
    });
  } else {
    initVideoPreview();
    lazyLoadVideos();
  }

  /**
   * Re-initialize after dynamic content load (market.js)
   */
  window.addEventListener('market:items-loaded', () => {
    console.log('[VIDEO] Re-initializing after items load');
    initVideoPreview();
    lazyLoadVideos();
  });

  // Export for manual initialization
  window.videoPreview = {
    init: initVideoPreview,
    lazyLoad: lazyLoadVideos
  };

})();
