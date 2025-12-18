/**
 * 📦 PROOFLY UPLOAD MANAGER
 * 
 * Handles background file uploads with:
 * - Draft item creation
 * - Progress tracking (0-100%)
 * - Direct upload to Cloudinary/R2
 * - LocalStorage persistence (survives page navigation)
 * - Fixed top progress bar
 * 
 * Flow:
 *   1. User clicks "Publish" → createDraft() → get item_id
 *   2. Redirect to /market immediately
 *   3. Upload files in background → updateProgress()
 *   4. Complete → attachFiles() → item published
 */

class UploadManager {
  constructor() {
    this.uploads = this.loadState();
    this.progressBar = null;
    this.init();
  }

  /**
   * Initialize upload manager
   * - Create global progress bar
   * - Resume pending uploads from localStorage
   */
  init() {
    // Create fixed top progress bar
    this.progressBar = document.createElement('div');
    this.progressBar.id = 'global-upload-progress';
    this.progressBar.style.cssText = `
      position: fixed;
      top: 0;
      left: 0;
      right: 0;
      height: 4px;
      background: linear-gradient(90deg, #667eea 0%, #764ba2 100%);
      transform: scaleX(0);
      transform-origin: left;
      transition: transform 0.3s ease;
      z-index: 10000;
      box-shadow: 0 2px 8px rgba(102, 126, 234, 0.4);
    `;
    document.body.appendChild(this.progressBar);

    // Resume pending uploads
    this.resumePendingUploads();
  }

  /**
   * Create draft item on server
   * 
   * @param {Object} formData - {title, price, tags, desc}
   * @returns {Promise<Object>} - {item_id, upload_urls}
   */
  async createDraft(formData) {
    try {
      const resp = await fetch('/api/market/items/draft', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        credentials: 'include',
        body: JSON.stringify(formData)
      });

      if (!resp.ok) {
        throw new Error(`Draft creation failed: ${resp.status}`);
      }

      const data = await resp.json();
      
      if (!data.ok) {
        throw new Error(data.error || 'Unknown error');
      }

      // Save to state
      this.uploads[data.item_id] = {
        item_id: data.item_id,
        title: formData.title,
        progress: 0,
        status: 'uploading',
        upload_urls: data.upload_urls,
        created_at: Date.now()
      };
      this.saveState();

      console.log('[UPLOAD] Draft created:', data.item_id);
      
      return data;
    } catch (error) {
      console.error('[UPLOAD] Draft creation failed:', error);
      throw error;
    }
  }

  /**
   * Upload single file with progress tracking
   * 
   * @param {number} itemId - Draft item ID
   * @param {File} file - File object to upload
   * @param {string} type - 'video' | 'stl' | 'zip' | 'cover'
   * @returns {Promise<string>} - Uploaded file URL
   */
  async uploadFile(itemId, file, type) {
    const upload = this.uploads[itemId];
    if (!upload) {
      throw new Error('Upload not found in state');
    }

    const uploadUrl = upload.upload_urls[type];
    if (!uploadUrl) {
      console.warn(`[UPLOAD] No upload URL for ${type}, skipping`);
      return null;
    }

    return new Promise((resolve, reject) => {
      const xhr = new XMLHttpRequest();

      // Track upload progress
      xhr.upload.addEventListener('progress', (e) => {
        if (e.lengthComputable) {
          const percent = Math.round((e.loaded / e.total) * 100);
          this.updateProgress(itemId, percent);
        }
      });

      xhr.addEventListener('load', () => {
        if (xhr.status >= 200 && xhr.status < 300) {
          try {
            const result = JSON.parse(xhr.responseText);
            const url = result.secure_url || result.url || null;
            console.log(`[UPLOAD] ${type} uploaded:`, url);
            resolve(url);
          } catch {
            resolve(null);
          }
        } else {
          reject(new Error(`Upload failed: ${xhr.status}`));
        }
      });

      xhr.addEventListener('error', () => {
        reject(new Error('Network error during upload'));
      });

      xhr.addEventListener('abort', () => {
        reject(new Error('Upload aborted'));
      });

      // Prepare form data
      const formData = new FormData();
      formData.append('file', file);

      // Send upload
      xhr.open('POST', uploadUrl);
      xhr.send(formData);
    });
  }

  /**
   * Update upload progress
   * 
   * @param {number} itemId - Draft item ID
   * @param {number} percent - Progress 0-100
   */
  updateProgress(itemId, percent) {
    if (!this.uploads[itemId]) return;

    this.uploads[itemId].progress = percent;
    this.saveState();

    // Update visual progress bar
    this.progressBar.style.transform = `scaleX(${percent / 100})`;

    // Notify backend
    fetch(`/api/market/items/${itemId}/progress`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify({
        progress: percent,
        status: 'uploading'
      })
    }).catch(err => {
      console.warn('[UPLOAD] Progress update failed:', err);
    });
  }

  /**
   * Complete upload and publish item
   * 
   * @param {number} itemId - Draft item ID
   * @param {Object} urls - {video_url, stl_url, zip_url, cover_url, gallery_urls}
   */
  async completeUpload(itemId, urls) {
    try {
      const resp = await fetch(`/api/market/items/${itemId}/attach`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify(urls)
      });

      if (!resp.ok) {
        throw new Error(`Attach failed: ${resp.status}`);
      }

      const data = await resp.json();

      if (!data.ok) {
        throw new Error(data.error || 'Attach failed');
      }

      console.log('[UPLOAD] Item published:', itemId);

      // Cleanup state
      delete this.uploads[itemId];
      this.saveState();

      // Hide progress bar
      this.progressBar.style.transform = 'scaleX(0)';

      // Show success toast
      if (window.toast) {
        window.toast('Модель опублікована!', 'success');
      }

      return data;
    } catch (error) {
      console.error('[UPLOAD] Complete failed:', error);
      throw error;
    }
  }

  /**
   * Resume pending uploads after page reload
   */
  resumePendingUploads() {
    const pending = Object.values(this.uploads);
    
    if (pending.length === 0) return;

    console.log('[UPLOAD] Found pending uploads:', pending.length);

    // Show progress bar for first pending upload
    const first = pending[0];
    if (first.progress > 0) {
      this.progressBar.style.transform = `scaleX(${first.progress / 100})`;
    }
  }

  /**
   * Cancel upload
   * 
   * @param {number} itemId - Draft item ID
   */
  cancelUpload(itemId) {
    if (this.uploads[itemId]) {
      delete this.uploads[itemId];
      this.saveState();
      this.progressBar.style.transform = 'scaleX(0)';
      console.log('[UPLOAD] Cancelled:', itemId);
    }
  }

  /**
   * Load state from localStorage
   * 
   * @returns {Object} - Upload state
   */
  loadState() {
    try {
      const state = localStorage.getItem('proofly_uploads');
      return state ? JSON.parse(state) : {};
    } catch {
      return {};
    }
  }

  /**
   * Save state to localStorage
   */
  saveState() {
    try {
      localStorage.setItem('proofly_uploads', JSON.stringify(this.uploads));
    } catch (error) {
      console.warn('[UPLOAD] Failed to save state:', error);
    }
  }

  /**
   * Get current upload status
   * 
   * @param {number} itemId - Draft item ID
   * @returns {Object|null} - Upload state or null
   */
  getStatus(itemId) {
    return this.uploads[itemId] || null;
  }

  /**
   * Get all pending uploads
   * 
   * @returns {Array} - Array of upload states
   */
  getPendingUploads() {
    return Object.values(this.uploads);
  }
}

// Initialize global singleton
if (!window.uploadManager) {
  window.uploadManager = new UploadManager();
  console.log('[UPLOAD] Upload manager initialized');
}

export default window.uploadManager;
