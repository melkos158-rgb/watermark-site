/**
 * REVIEWS v2 - User reviews with photos
 * Handles fetching, rendering, submitting, and deleting reviews
 */

(function() {
  'use strict';

  let currentItemId = null;

  // DOM elements
  const section = document.getElementById('reviews-section');
  const list = document.getElementById('reviewsList');
  const emptyState = document.getElementById('reviewsEmpty');
  const reviewForm = document.getElementById('reviewForm');

  /**
   * Initialize reviews functionality
   */
  function init() {
    if (!section) return;

    // Get item ID from data attribute
    currentItemId = parseInt(section.dataset.itemId, 10);
    if (!currentItemId) {
      console.error('Reviews: No item ID found');
      return;
    }

    // Load reviews
    loadReviews();

    // Setup review form if present
    if (reviewForm) {
      reviewForm.addEventListener('submit', handleSubmit);
    }
  }

  /**
   * Load reviews from API
   */
  async function loadReviews() {
    if (!currentItemId) return;

    try {
      const response = await fetch(`/api/item/${currentItemId}/reviews?limit=50`);
      
      if (!response.ok) {
        console.error('Failed to load reviews:', response.status);
        showEmpty();
        return;
      }

      const data = await response.json();
      
      if (!data.ok || !data.reviews) {
        console.error('Invalid reviews response:', data);
        showEmpty();
        return;
      }

      if (data.reviews.length === 0) {
        showEmpty();
      } else {
        renderReviews(data.reviews);
      }

    } catch (err) {
      console.error('Error loading reviews:', err);
      showEmpty();
    }
  }

  /**
   * Render reviews list
   */
  function renderReviews(reviews) {
    if (!list) return;

    list.innerHTML = '';
    
    if (emptyState) {
      emptyState.style.display = 'none';
    }

    reviews.forEach(review => {
      const card = createReviewCard(review);
      list.appendChild(card);
    });
  }

  /**
   * Create review card element
   */
  function createReviewCard(review) {
    const card = document.createElement('div');
    card.className = 'review-card';
    card.dataset.reviewId = review.id;

    // Header with author info and rating
    const header = document.createElement('div');
    header.className = 'review-header';

    // Author
    const author = document.createElement('div');
    author.className = 'review-author';

    const avatar = document.createElement('img');
    avatar.className = 'review-author-avatar';
    avatar.src = review.author_avatar || '/static/img/user.jpg';
    avatar.alt = review.author_name || 'User';
    author.appendChild(avatar);

    const authorInfo = document.createElement('div');
    authorInfo.className = 'review-author-info';

    const authorName = document.createElement('div');
    authorName.className = 'review-author-name';
    authorName.textContent = review.author_name || 'Anonymous';
    authorInfo.appendChild(authorName);

    // Date
    if (review.created_at) {
      const date = document.createElement('div');
      date.className = 'review-date';
      date.textContent = formatDate(review.created_at);
      authorInfo.appendChild(date);
    }

    author.appendChild(authorInfo);
    header.appendChild(author);

    // Rating stars
    const stars = document.createElement('div');
    stars.className = 'review-stars';
    stars.textContent = '⭐'.repeat(review.rating || 0);
    header.appendChild(stars);

    card.appendChild(header);

    // Review text
    if (review.text && review.text.trim()) {
      const text = document.createElement('p');
      text.className = 'review-text';
      text.textContent = review.text;
      card.appendChild(text);
    }

    // Review image
    if (review.image_url) {
      const img = document.createElement('img');
      img.className = 'review-image';
      img.src = review.image_url;
      img.alt = 'Review image';
      img.loading = 'lazy';
      card.appendChild(img);
    }

    // Delete button (only for owner)
    if (review.is_owner) {
      const deleteBtn = document.createElement('button');
      deleteBtn.className = 'review-delete';
      deleteBtn.textContent = 'Delete';
      deleteBtn.onclick = () => handleDelete(review.id);
      card.appendChild(deleteBtn);
    }

    return card;
  }

  /**
   * Format date to readable string
   */
  function formatDate(dateStr) {
    try {
      const date = new Date(dateStr);
      return date.toLocaleDateString('en-US', { 
        year: 'numeric', 
        month: 'short', 
        day: 'numeric' 
      });
    } catch (e) {
      return dateStr;
    }
  }

  /**
   * Show empty state
   */
  function showEmpty() {
    if (!list || !emptyState) return;
    
    list.innerHTML = '';
    emptyState.style.display = 'block';
  }

  /**
   * Handle review form submission
   */
  async function handleSubmit(e) {
    e.preventDefault();

    const ratingSelect = document.getElementById('reviewRating');
    const textInput = document.getElementById('reviewText');
    const imageInput = document.getElementById('reviewImage');

    if (!ratingSelect || !ratingSelect.value) {
      alert('Please select a rating');
      return;
    }

    const formData = new FormData();
    formData.append('rating', ratingSelect.value);
    
    if (textInput && textInput.value.trim()) {
      formData.append('text', textInput.value.trim());
    }
    
    if (imageInput && imageInput.files && imageInput.files[0]) {
      formData.append('image', imageInput.files[0]);
    }

    // Disable form
    const submitBtn = reviewForm.querySelector('button[type="submit"]');
    if (submitBtn) {
      submitBtn.disabled = true;
      submitBtn.textContent = 'Submitting...';
    }

    try {
      const response = await fetch(`/api/item/${currentItemId}/reviews`, {
        method: 'POST',
        body: formData
      });

      if (response.status === 401) {
        const currentPath = window.location.pathname;
        window.location.href = `/login?next=${encodeURIComponent(currentPath)}`;
        return;
      }

      if (!response.ok) {
        throw new Error(`Submit failed: ${response.status}`);
      }

      const data = await response.json();

      if (!data.ok) {
        throw new Error(data.error || 'Submit failed');
      }

      // Reset form
      reviewForm.reset();

      // Reload reviews
      await loadReviews();

      // Update rating display on page if element exists
      updatePageRating();

      // Show success
      if (submitBtn) {
        submitBtn.textContent = '✅ Submitted!';
        setTimeout(() => {
          submitBtn.textContent = 'Submit Review';
        }, 2000);
      }

    } catch (err) {
      console.error('Submit error:', err);
      alert('Failed to submit review: ' + err.message);
    } finally {
      // Re-enable form
      if (submitBtn) {
        submitBtn.disabled = false;
      }
    }
  }

  /**
   * Handle delete review
   */
  async function handleDelete(reviewId) {
    if (!confirm('Delete this review?')) {
      return;
    }

    try {
      const response = await fetch(`/api/review/${reviewId}`, {
        method: 'DELETE'
      });

      if (response.status === 401) {
        const currentPath = window.location.pathname;
        window.location.href = `/login?next=${encodeURIComponent(currentPath)}`;
        return;
      }

      if (response.status === 403) {
        alert('You can only delete your own reviews');
        return;
      }

      if (!response.ok) {
        throw new Error(`Delete failed: ${response.status}`);
      }

      const data = await response.json();

      if (!data.ok) {
        throw new Error(data.error || 'Delete failed');
      }

      // Reload reviews
      await loadReviews();

      // Update rating display on page
      updatePageRating();

    } catch (err) {
      console.error('Delete error:', err);
      alert('Failed to delete review: ' + err.message);
    }
  }

  /**
   * Update rating display on page after review submission/deletion
   */
  function updatePageRating() {
    // Try to find rating display elements and refresh them
    // This is optional - depends on page structure
    
    // Example: if there's a .meta element with rating
    const metaEl = document.querySelector('.detail-head .meta');
    if (metaEl) {
      // Could reload item data and update, but for now just trigger page reload
      // or fetch item rating separately
      
      // Simple approach: reload page after 1 second
      setTimeout(() => {
        window.location.reload();
      }, 1000);
    }
  }

  // Initialize on DOM ready
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

})();
