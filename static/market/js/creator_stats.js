/**
 * Creator Stats Module
 * Loads and displays creator reputation metrics on item detail page
 * 
 * Features:
 * - Compact trust badges in header (Avg quality, Auto presets %)
 * - Full reputation card in author section (All metrics + icons)
 * - Single API call with graceful degradation
 * - 5-minute cache via HTTP Cache-Control
 */

(function() {
  'use strict';

  // Get creator username from data attribute
  const authorLink = document.querySelector('a.author[data-creator]');
  const creatorUsername = authorLink?.dataset.creator;
  
  if (!creatorUsername) {
    console.log('Creator username not found, skipping reputation load');
    return;
  }

  // Fetch creator stats from API
  fetch(`/api/creator/${encodeURIComponent(creatorUsername)}/stats`)
    .then(res => {
      if (!res.ok) {
        throw new Error(`HTTP ${res.status}`);
      }
      return res.json();
    })
    .then(data => {
      if (!data.ok) {
        throw new Error(data.error || 'API error');
      }
      
      // Render compact badges in header
      renderCompactBadges(data);
      
      // Render full reputation card in author section
      renderReputationCard(data);
    })
    .catch(err => {
      console.warn('Failed to load creator stats:', err);
      // Silently fail - badges just won't appear
    });

  /**
   * Render compact trust badges in header author link
   */
  function renderCompactBadges(stats) {
    const badgesContainer = document.querySelector('.creator-trust-badges');
    if (!badgesContainer) return;

    const badges = [];
    
    // Avg Proof Score badge (if > 0)
    if (stats.avg_proof_score > 0) {
      badges.push(`
        <span class="trust-badge">
          <span class="icon">⭐</span>
          <span>${stats.avg_proof_score}</span>
        </span>
      `);
    }
    
    // Auto presets coverage badge (if > 0)
    if (stats.presets_coverage_percent > 0) {
      badges.push(`
        <span class="trust-badge">
          <span class="icon">🎯</span>
          <span>${stats.presets_coverage_percent}%</span>
        </span>
      `);
    }
    
    if (badges.length > 0) {
      badgesContainer.innerHTML = badges.join('');
    }
  }

  /**
   * Render full reputation card in author section
   */
  function renderReputationCard(stats) {
    const repCard = document.querySelector('.creator-reputation');
    if (!repCard) return;

    // Update proof score badge
    const proofScoreBadge = repCard.querySelector('.proof-score-badge .value');
    if (proofScoreBadge) {
      proofScoreBadge.textContent = stats.avg_proof_score > 0 
        ? `${stats.avg_proof_score}/100` 
        : 'Not rated';
    }
    
    // Update presets coverage badge
    const presetsBadge = repCard.querySelector('.presets-badge .value');
    if (presetsBadge) {
      presetsBadge.textContent = stats.presets_coverage_percent > 0
        ? `${stats.presets_coverage_percent}%`
        : 'None';
    }
    
    // Update total items badge
    const totalItemsBadge = repCard.querySelector('.total-items-badge .value');
    if (totalItemsBadge) {
      totalItemsBadge.textContent = stats.total_items || 0;
    }
    
    // Show the card
    repCard.style.display = 'block';
  }

})();
