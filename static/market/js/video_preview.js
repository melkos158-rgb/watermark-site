/**
 * 🎬 PROOFLY VIDEO PREVIEW
 * 
 * Cults-style video preview on market cards:
 * - Desktop: hover → play, leave → pause
 * - Mobile: tap → toggle play/pause
 * - IntersectionObserver: auto-pause when card leaves viewport
 * - Performance: only play videos in viewport
 */

(function() {
  'use strict';
  
  // Prevent double initialization
  if (window.__videoPreviewInitialized) return;
  window.__videoPreviewInitialized = true;

  const isMobile = /Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i.test(navigator.userAgent);
  const videos = new Map(); // Store video states

  /**
   * Initialize video preview system
   */
  function init() {
    // Find all video previews
    const videoElements = document.querySelectorAll('[data-video-preview]');
    
    if (videoElements.length === 0) {
      console.log('[VIDEO] No video previews found on page');
      return;
    }

    console.log(`[VIDEO] Initializing ${videoElements.length} video previews`);

    // Setup IntersectionObserver for viewport tracking
    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach(entry => {
          const video = entry.target;
          const card = video.closest('.card-preview');
          
          if (entry.isIntersecting) {
            // Card entered viewport
            video.dataset.inview = '1';
            if (card) card.dataset.inview = '1';
          } else {
            // Card left viewport - auto-pause
            video.dataset.inview = '0';
            if (card) card.dataset.inview = '0';
            
            if (!video.paused) {
              video.pause();
              video.classList.remove('is-playing');
              console.log('[VIDEO] Auto-paused (left viewport)');
            }
          }
        });
      },
      {
        root: null,
        rootMargin: '50px', // Start loading slightly before visible
        threshold: 0.2 // 20% visible
      }
    );

    // Initialize each video
    videoElements.forEach(video => {
      const card = video.closest('.card-preview');
      if (!card) return;

      // Mark card as having video (for CSS ::after mute icon)
      card.setAttribute('data-has-video', 'true');

      // Mark video as loading initially
      video.setAttribute('data-loading', '1');

      // Remove loading state when metadata loads
      video.addEventListener('loadedmetadata', () => {
        video.removeAttribute('data-loading');
      }, { once: true });

      // Store initial state
      videos.set(video, {
        isPlaying: false,
        card: card
      });

      // Observe for viewport visibility
      observer.observe(video);

      if (isMobile) {
        // Mobile: tap to toggle play/pause
        card.addEventListener('click', (e) => {
          // Don't interfere with link clicks on badges, etc.
          if (e.target.closest('.badge, .card-like')) return;
          
          e.preventDefault();
          e.stopPropagation();
          
          toggleVideo(video);
        });
      } else {
        // Desktop: hover to play
        card.addEventListener('mouseenter', () => {
          playVideo(video);
        });

        card.addEventListener('mouseleave', () => {
          pauseVideo(video);
        });
      }
    });

    console.log('[VIDEO] Video preview system initialized');
  }

  /**
   * Play video if in viewport
   */
  function playVideo(video) {
    if (video.dataset.inview !== '1') {
      console.log('[VIDEO] Skipping play - not in viewport');
      return;
    }

    if (video.paused) {
      const playPromise = video.play();
      
      if (playPromise !== undefined) {
        playPromise
          .then(() => {
            video.classList.add('is-playing');
            const state = videos.get(video);
            if (state) state.isPlaying = true;
          })
          .catch(err => {
            console.warn('[VIDEO] Play failed:', err);
          });
      }
    }
  }

  /**
   * Pause video and reset (or keep position)
   */
  function pauseVideo(video, reset = false) {
    if (!video.paused) {
      video.pause();
      video.classList.remove('is-playing');
      
      // Optional: reset to start on pause
      if (reset) {
        video.currentTime = 0;
      }
      
      const state = videos.get(video);
      if (state) state.isPlaying = false;
    }
  }

  /**
   * Toggle play/pause (mobile)
   */
  function toggleVideo(video) {
    if (video.dataset.inview !== '1') {
      console.log('[VIDEO] Not in viewport');
      return;
    }

    if (video.paused) {
      playVideo(video);
    } else {
      pauseVideo(video);
    }
  }

  // Initialize on DOM ready
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

  // Re-init on dynamic content load (for infinite scroll, etc.)
  window.addEventListener('market:cardsLoaded', () => {
    console.log('[VIDEO] Reinitializing for new cards');
    init();
  });
})();
