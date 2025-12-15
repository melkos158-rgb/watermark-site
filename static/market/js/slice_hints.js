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

  let cachedHints = null;

  // Setup copy button event listener once
  if (copyBtn) {
    copyBtn.addEventListener('click', copyHintsToClipboard);
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

    } catch (err) {
      console.error('Failed to load slice hints:', err);
      showError();
    }
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
