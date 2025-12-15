/**
 * Slice Hints - Recommended Print Settings
 * Fetches and displays auto-generated print settings from /api/item/<id>/slice-hints
 */

(function() {
  'use strict';

  const card = document.getElementById('print-settings-card');
  if (!card) return;

  const itemId = card.getAttribute('data-item-id');
  if (!itemId) return;

  const bodyEl = document.getElementById('print-settings-body');
  const copyBtn = document.getElementById('btn-copy-slice-hints');
  const curaBtn = document.getElementById('btn-download-cura');
  const prusaBtn = document.getElementById('btn-download-prusa');
  const nozzleSelect = document.getElementById('slice-nozzle');
  const qualitySelect = document.getElementById('slice-quality');

  let cachedHints = null;

  // Setup copy button event listener once
  if (copyBtn) {
    copyBtn.addEventListener('click', copyHintsToClipboard);
  }

  // Setup profile selector listeners once
  if (nozzleSelect) {
    nozzleSelect.addEventListener('change', onProfileChange);
  }
  if (qualitySelect) {
    qualitySelect.addEventListener('change', onProfileChange);
  }

  // Load slice hints on page load
  loadSliceHints();

  async function loadSliceHints() {
    try {
      const resp = await fetch(`/api/item/${itemId}/slice-hints`);
      const data = await resp.json();

      if (!data.ok || !data.slice_hints || Object.keys(data.slice_hints).length === 0) {
        showNoData();
        return;
      }

      cachedHints = data.slice_hints;
      renderHints(cachedHints);
      card.style.display = 'block';
      
      if (copyBtn) {
        copyBtn.disabled = false;
      }
      
      // Enable download buttons with correct URLs
      enableDownloadButtons();

    } catch (err) {
      console.error('Failed to load slice hints:', err);
      showError();
    }
  }

  function enableDownloadButtons() {
    updateDownloadUrls();
  }

  function updateDownloadUrls() {
    const nozzle = nozzleSelect ? nozzleSelect.value : '0.4';
    const quality = qualitySelect ? qualitySelect.value : 'normal';
    const params = `&nozzle=${nozzle}&quality=${quality}`;
    
    if (curaBtn) {
      curaBtn.href = `/api/item/${itemId}/slice-hints/preset?target=cura${params}`;
      curaBtn.style.pointerEvents = 'auto';
      curaBtn.style.opacity = '1';
    }
    
    if (prusaBtn) {
      prusaBtn.href = `/api/item/${itemId}/slice-hints/preset?target=prusa${params}`;
      prusaBtn.style.pointerEvents = 'auto';
      prusaBtn.style.opacity = '1';
    }
  }

  function onProfileChange() {
    if (!cachedHints) return;
    
    // Apply modifiers and re-render
    const modified = applyProfileModifiers(cachedHints);
    renderHints(modified);
    updateDownloadUrls();
  }

  function applyProfileModifiers(hints) {
    const modified = Object.assign({}, hints);
    
    const nozzle = parseFloat(nozzleSelect ? nozzleSelect.value : '0.4');
    const quality = qualitySelect ? qualitySelect.value : 'normal';
    
    let layerHeight = modified.layer_height || 0.2;
    let estimatedTime = modified.estimated_time_hours || 0;
    
    // Apply quality modifier
    if (quality === 'fine') {
      layerHeight *= 0.8;
    } else if (quality === 'draft') {
      layerHeight *= 1.2;
    }
    
    // Apply nozzle modifier
    if (Math.abs(nozzle - 0.6) < 0.01) { // nozzle == 0.6
      layerHeight = Math.min(layerHeight + 0.04, 0.32);
      estimatedTime *= 0.85;
    }
    
    // Clamp layer height
    layerHeight = Math.max(0.12, Math.min(layerHeight, 0.32));
    
    modified.layer_height = Math.round(layerHeight * 100) / 100;
    modified.estimated_time_hours = Math.round(estimatedTime * 10) / 10;
    
    return modified;
  }

  function showNoData() {
    bodyEl.innerHTML = '<p class="muted">No recommendations yet. Upload a valid STL to get print settings.</p>';
    card.style.display = 'block';
  }

  function showError() {
    bodyEl.innerHTML = '<p class="muted">Failed to load recommendations.</p>';
    card.style.display = 'block';
  }

  function renderHints(hints) {
    const rows = [];

    // Layer height
    if (hints.layer_height !== undefined) {
      rows.push(`<div class="setting-row">
        <span class="label">Layer height:</span>
        <span class="value">${hints.layer_height} mm</span>
      </div>`);
    }

    // Infill
    if (hints.infill_percent !== undefined) {
      rows.push(`<div class="setting-row">
        <span class="label">Infill:</span>
        <span class="value">${hints.infill_percent}%</span>
      </div>`);
    }

    // Supports
    if (hints.supports) {
      const supportsLabel = formatSupports(hints.supports);
      rows.push(`<div class="setting-row">
        <span class="label">Supports:</span>
        <span class="value">${supportsLabel}</span>
      </div>`);
    }

    // Material
    if (hints.material) {
      rows.push(`<div class="setting-row">
        <span class="label">Material:</span>
        <span class="value">${hints.material}</span>
      </div>`);
    }

    // Estimated time
    if (hints.estimated_time_hours !== undefined) {
      rows.push(`<div class="setting-row">
        <span class="label">Est. time:</span>
        <span class="value">${hints.estimated_time_hours} h</span>
      </div>`);
    }

    // Warnings
    if (hints.warnings && hints.warnings.length > 0) {
      const warningBadges = hints.warnings.map(w => {
        const escaped = escapeHtml(w);
        return `<span class="warning-badge">⚠️ ${escaped}</span>`;
      }).join('');
      rows.push(`<div class="setting-row warnings">
        <span class="label">Warnings:</span>
        <div class="warning-list">${warningBadges}</div>
      </div>`);
    }

    bodyEl.innerHTML = rows.join('');
  }

  function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
  }

  function formatSupports(supports) {
    const map = {
      'none': 'None',
      'buildplate': 'Build plate only',
      'everywhere': 'Everywhere'
    };
    return map[supports] || supports;
  }

  function copyHintsToClipboard() {
    if (!cachedHints) return;

    const text = buildCopyText(cachedHints);

    // Modern clipboard API
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text)
        .then(() => {
          showCopyFeedback('Copied!');
        })
        .catch(() => {
          fallbackCopy(text);
        });
    } else {
      fallbackCopy(text);
    }
  }

  function buildCopyText(hints) {
    let lines = ['Proofly Slice Hints', ''];

    if (hints.layer_height !== undefined) {
      lines.push(`Layer height: ${hints.layer_height} mm`);
    }
    if (hints.infill_percent !== undefined) {
      lines.push(`Infill: ${hints.infill_percent}%`);
    }
    if (hints.supports) {
      lines.push(`Supports: ${formatSupports(hints.supports)}`);
    }
    if (hints.material) {
      lines.push(`Material: ${hints.material}`);
    }
    if (hints.estimated_time_hours !== undefined) {
      lines.push(`Est. time: ${hints.estimated_time_hours} h`);
    }
    if (hints.warnings && hints.warnings.length > 0) {
      lines.push('');
      lines.push('Warnings:');
      hints.warnings.forEach(w => lines.push(`  - ${w}`));
    }

    return lines.join('\n');
  }

  function fallbackCopy(text) {
    const textarea = document.createElement('textarea');
    textarea.value = text;
    textarea.style.position = 'fixed';
    textarea.style.opacity = '0';
    document.body.appendChild(textarea);
    textarea.select();
    
    try {
      document.execCommand('copy');
      showCopyFeedback('Copied!');
    } catch (err) {
      console.error('Copy failed:', err);
      showCopyFeedback('Copy failed');
    }
    
    document.body.removeChild(textarea);
  }

  function showCopyFeedback(msg) {
    if (!copyBtn) return;
    const originalText = copyBtn.textContent;
    copyBtn.textContent = msg;
    setTimeout(() => {
      copyBtn.textContent = originalText;
    }, 2000);
  }

})();
