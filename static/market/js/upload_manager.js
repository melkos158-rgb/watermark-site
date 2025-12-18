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

// ✅ Single source of truth for large file threshold
const LARGE_FILE_THRESHOLD = 15 * 1024 * 1024; // 15MB

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
        cloudinary: data.cloudinary || null,  // Store Cloudinary config
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
   * Supports:
   * - Cloudinary unsigned upload (video/cover) with preset + folder
   * - Chunked upload for large files (stl/zip) 8MB chunks
   * - Simple upload fallback
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

    // Check if Cloudinary upload
    const isCloudinary = uploadUrl.includes('api.cloudinary.com');
    
    // ✅ Force chunking for large ZIP/STL files (>15MB)
    const needsChunking = (type === 'zip' || type === 'stl') && !isCloudinary && file.size > LARGE_FILE_THRESHOLD;
    
    if (needsChunking) {
      console.log(`[UPLOAD] Large ${type} file (${(file.size / 1024 / 1024).toFixed(1)}MB) → using chunked upload`);
      return this.uploadFileChunked(itemId, file, type, uploadUrl);
    }

    // Simple upload (Cloudinary or small files)
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

      // Add Cloudinary-specific fields
      if (isCloudinary && upload.cloudinary) {
        // Add unsigned upload preset (if available)
        if (upload.cloudinary.unsigned_preset) {
          formData.append('upload_preset', upload.cloudinary.unsigned_preset);
        }
        
        // Add folder for organization
        formData.append('folder', `proofly/items/${itemId}`);
        
        console.log(`[UPLOAD] Cloudinary upload: preset=${upload.cloudinary.unsigned_preset} folder=proofly/items/${itemId}`);
      }

      // Send upload
      xhr.open('POST', uploadUrl);
      xhr.send(formData);
    });
  }

  /**
   * Upload large file in chunks (8MB each)
   * 
   * @param {number} itemId - Draft item ID
   * @param {File} file - File object to upload
   * @param {string} type - 'stl' | 'zip'
   * @param {string} uploadUrl - Chunk upload endpoint
   * @returns {Promise<string>} - Uploaded file URL
   */
  async uploadFileChunked(itemId, file, type, uploadUrl) {
    const CHUNK_SIZE = 8 * 1024 * 1024; // 8MB
    const totalChunks = Math.ceil(file.size / CHUNK_SIZE);
    const uploadId = this.generateUploadId();
    
    console.log(`[CHUNK] Starting chunked upload: file=${file.name} size=${file.size} chunks=${totalChunks}`);
    
    let uploadedBytes = 0;
    
    for (let i = 0; i < totalChunks; i++) {
      const start = i * CHUNK_SIZE;
      const end = Math.min(start + CHUNK_SIZE, file.size);
      const chunk = file.slice(start, end);
      
      // Upload chunk
      const result = await this.uploadChunk(
        uploadUrl,
        chunk,
        uploadId,
        i,
        totalChunks,
        file.name
      );
      
      // Update progress based on uploaded bytes
      uploadedBytes += chunk.size;
      const percent = Math.round((uploadedBytes / file.size) * 100);
      this.updateProgress(itemId, percent);
      
      console.log(`[CHUNK] Uploaded ${i + 1}/${totalChunks} (${percent}%)`);
      
      // If last chunk, return URL
      if (result.done && result.url) {
        console.log(`[CHUNK] ✅ Upload complete: ${result.url}`);
        return result.url;
      }
    }
    
    throw new Error('Chunked upload incomplete');
  }

  /**
   * Upload single chunk
   * 
   * @param {string} url - Upload endpoint
   * @param {Blob} chunk - Chunk data
   * @param {string} uploadId - Upload session ID
   * @param {number} index - Chunk index (0-based)
   * @param {number} total - Total chunks
   * @param {string} filename - Original filename
   * @returns {Promise<Object>} - {ok, done, url?, received, total}
   */
  uploadChunk(url, chunk, uploadId, index, total, filename) {
    console.log(`[CHUNK] 🚀 START chunk=${index+1}/${total} size=${chunk.size} url=${url}`);
    
    return new Promise((resolve, reject) => {
      const xhr = new XMLHttpRequest();
      
      xhr.addEventListener('load', () => {
        console.log(`[CHUNK] ✅ LOAD chunk=${index+1}/${total} status=${xhr.status}`);
        if (xhr.status >= 200 && xhr.status < 300) {
          try {
            const result = JSON.parse(xhr.responseText);
            resolve(result);
          } catch (e) {
            console.error(`[CHUNK] ❌ PARSE ERROR chunk=${index+1}:`, e);
            reject(new Error('Invalid server response'));
          }
        } else {
          console.error(`[CHUNK] ❌ HTTP ERROR chunk=${index+1} status=${xhr.status}`);
          reject(new Error(`Chunk upload failed: ${xhr.status}`));
        }
      });
      
      xhr.addEventListener('error', () => {
        console.error(`[CHUNK] ❌ NETWORK ERROR chunk=${index+1}`);
        reject(new Error('Network error during chunk upload'));
      });
      
      xhr.addEventListener('abort', () => {
        console.error(`[CHUNK] ⛔ ABORT chunk=${index+1} - likely navigation/redirect killed XHR`);
        reject(new Error('Chunk upload aborted'));
      });
      
      // Set chunk headers
      xhr.open('POST', url);
      xhr.setRequestHeader('X-Upload-Id', uploadId);
      xhr.setRequestHeader('X-Chunk-Index', index.toString());
      xhr.setRequestHeader('X-Chunk-Total', total.toString());
      xhr.setRequestHeader('X-File-Name', filename);
      
      // Send raw chunk data (not FormData for chunks)
      xhr.send(chunk);
    });
  }

  /**
   * Generate unique upload ID (uuid)
   * 
   * @returns {string} - UUID v4
   */
  generateUploadId() {
    return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
      const r = Math.random() * 16 | 0;
      const v = c === 'x' ? r : (r & 0x3 | 0x8);
      return v.toString(16);
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

    // Notify backend with keepalive (survives page navigation)
    const url = `/api/market/items/${itemId}/progress`;
    const payload = {
      progress: percent,
      status: 'uploading'
    };
    
    console.log(`[UPLOAD] Progress update: ${percent}% → ${url}`);
    
    fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      keepalive: true,  // ✅ Survives page navigation
      body: JSON.stringify(payload)
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
      const url = `/api/market/items/${itemId}/attach`;
      
      console.log(`[UPLOAD] Attaching files → ${url}`, urls);
      
      const resp = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        keepalive: true,  // ✅ Survives page navigation
        body: JSON.stringify(urls)
      });

      if (!resp.ok) {
        console.error(`[UPLOAD] Attach failed: status=${resp.status}`);
        throw new Error(`Attach failed: ${resp.status}`);
      }

      const data = await resp.json();

      if (!data.ok) {
        console.error('[UPLOAD] Attach rejected:', data.error);
        throw new Error(data.error || 'Attach failed');
      }

      console.log(`[UPLOAD] ✅ Item published: ${itemId}`);

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

// ✅ Expose threshold constant for upload.html to use
window.UPLOAD_LARGE_FILE_THRESHOLD = LARGE_FILE_THRESHOLD;

export default window.uploadManager;
