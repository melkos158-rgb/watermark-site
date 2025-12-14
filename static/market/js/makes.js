/**
 * MAKES v1 - User-uploaded photos of printed models
 * Handles fetching, rendering, uploading, and deleting makes
 */

(function() {
  'use strict';

  let currentItemId = null;

  // DOM elements
  const section = document.getElementById('makes-section');
  const grid = document.getElementById('makesGrid');
  const emptyState = document.getElementById('makesEmpty');
  const uploadForm = document.getElementById('makeUploadForm');

  /**
   * Initialize makes functionality
   */
  function init() {
    if (!section) return;

    // Get item ID from data attribute
    currentItemId = parseInt(section.dataset.itemId, 10);
    if (!currentItemId) {
      console.error('Makes: No item ID found');
      return;
    }

    // Load makes
    loadMakes();

    // Setup upload form if present
    if (uploadForm) {
      uploadForm.addEventListener('submit', handleUpload);
    }
  }

  /**
   * Load makes from API
   */
  async function loadMakes() {
    if (!currentItemId) return;

    try {
      const response = await fetch(`/api/item/${currentItemId}/makes?limit=24&offset=0`);
      
      if (!response.ok) {
        console.error('Failed to load makes:', response.status);
        showEmpty();
        return;
      }

      const data = await response.json();
      
      if (!data.ok || !data.makes) {
        console.error('Invalid makes response:', data);
        showEmpty();
        return;
      }

      if (data.makes.length === 0) {
        showEmpty();
      } else {
        renderMakes(data.makes);
      }

    } catch (err) {
      console.error('Error loading makes:', err);
      showEmpty();
    }
  }

  /**
   * Render makes grid
   */
  function renderMakes(makes) {
    if (!grid) return;

    grid.innerHTML = '';
    
    if (emptyState) {
      emptyState.style.display = 'none';
    }

    makes.forEach(make => {
      const card = createMakeCard(make);
      grid.appendChild(card);
    });
  }

  /**
   * Create make card element
   */
  function createMakeCard(make) {
    const card = document.createElement('div');
    card.className = 'make-card';
    card.dataset.makeId = make.id;

    // Image
    const img = document.createElement('img');
    img.className = 'make-img';
    img.src = make.image_url || '/static/img/placeholder.jpg';
    img.alt = make.caption || 'User print';
    img.loading = 'lazy';
    card.appendChild(img);

    // Body
    const body = document.createElement('div');
    body.className = 'make-body';

    // Author info
    const author = document.createElement('div');
    author.className = 'make-author';

    const avatar = document.createElement('img');
    avatar.className = 'make-author-avatar';
    avatar.src = make.author_avatar || '/static/img/user.jpg';
    avatar.alt = make.author_name || 'User';
    author.appendChild(avatar);

    const authorName = document.createElement('span');
    authorName.className = 'make-author-name';
    authorName.textContent = make.author_name || 'Anonymous';
    author.appendChild(authorName);

    body.appendChild(author);

    // Caption (if exists)
    if (make.caption && make.caption.trim()) {
      const caption = document.createElement('p');
      caption.className = 'make-caption';
      caption.textContent = make.caption;
      body.appendChild(caption);
    }

    // Delete button (only for owner)
    if (make.is_owner) {
      const deleteBtn = document.createElement('button');
      deleteBtn.className = 'make-delete';
      deleteBtn.textContent = 'Delete';
      deleteBtn.onclick = () => handleDelete(make.id);
      body.appendChild(deleteBtn);
    }

    card.appendChild(body);
    return card;
  }

  /**
   * Show empty state
   */
  function showEmpty() {
    if (!grid || !emptyState) return;
    
    grid.innerHTML = '';
    emptyState.style.display = 'block';
  }

  /**
   * Handle upload form submission
   */
  async function handleUpload(e) {
    e.preventDefault();

    const imageInput = document.getElementById('makeImage');
    const captionInput = document.getElementById('makeCaption');

    if (!imageInput || !imageInput.files || !imageInput.files[0]) {
      alert('Please select an image');
      return;
    }

    const formData = new FormData();
    formData.append('image', imageInput.files[0]);
    
    if (captionInput && captionInput.value.trim()) {
      formData.append('caption', captionInput.value.trim());
    }

    // Disable form
    const submitBtn = uploadForm.querySelector('button[type="submit"]');
    if (submitBtn) {
      submitBtn.disabled = true;
      submitBtn.textContent = 'Uploading...';
    }

    try {
      const response = await fetch(`/api/item/${currentItemId}/makes`, {
        method: 'POST',
        body: formData
      });

      if (response.status === 401) {
        alert('Please log in to upload a make');
        window.location.href = '/login';
        return;
      }

      if (!response.ok) {
        throw new Error(`Upload failed: ${response.status}`);
      }

      const data = await response.json();

      if (!data.ok) {
        throw new Error(data.error || 'Upload failed');
      }

      // Reset form
      uploadForm.reset();

      // Reload makes
      await loadMakes();

      // Show success
      if (submitBtn) {
        submitBtn.textContent = '✅ Uploaded!';
        setTimeout(() => {
          submitBtn.textContent = 'Add Make';
        }, 2000);
      }

    } catch (err) {
      console.error('Upload error:', err);
      alert('Failed to upload make: ' + err.message);
    } finally {
      // Re-enable form
      if (submitBtn) {
        submitBtn.disabled = false;
      }
    }
  }

  /**
   * Handle delete make
   */
  async function handleDelete(makeId) {
    if (!confirm('Delete this make?')) {
      return;
    }

    try {
      const response = await fetch(`/api/make/${makeId}`, {
        method: 'DELETE'
      });

      if (response.status === 401) {
        alert('Please log in');
        window.location.href = '/login';
        return;
      }

      if (response.status === 403) {
        alert('You can only delete your own makes');
        return;
      }

      if (!response.ok) {
        throw new Error(`Delete failed: ${response.status}`);
      }

      const data = await response.json();

      if (!data.ok) {
        throw new Error(data.error || 'Delete failed');
      }

      // Reload makes
      await loadMakes();

    } catch (err) {
      console.error('Delete error:', err);
      alert('Failed to delete make: ' + err.message);
    }
  }

  // Initialize on DOM ready
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

})();
