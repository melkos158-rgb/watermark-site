/**
 * Conference Boost Features
 * - "Why this prints well" explainer based on printability data
 * - Sticky CTA for presets
 * 
 * ВАЖЛИВО: Використовує дані з window.printabilityData (встановлюється в detail.html)
 * щоб уникнути дублювання API запитів
 */

(function() {
  'use strict';

  const whySection = document.getElementById('why-prints-well');
  const whySummary = document.getElementById('why-summary');
  const whyBullets = document.getElementById('why-bullets');
  const stickyCTA = document.getElementById('sticky-cta');

  if (!whySection || !whySummary || !whyBullets) return;

  // Wait for printability data to be loaded by main script
  // Use polling with timeout
  let attempts = 0;
  const maxAttempts = 20; // 2 seconds max wait
  
  const checkInterval = setInterval(() => {
    attempts++;
    
    if (window.printabilityData) {
      clearInterval(checkInterval);
      processPrintabilityData(window.printabilityData);
    } else if (attempts >= maxAttempts) {
      clearInterval(checkInterval);
      showNeutralMessage();
    }
  }, 100);

  function processPrintabilityData(data) {
    if (!data.ok || !data.printability) {
      showNeutralMessage();
      return;
    }

    const p = data.printability;
    const score = data.proof_score || 0;

    // Generate summary line
    const summary = generateSummary(score);
    whySummary.textContent = summary;

    // Generate bullet points
    const bullets = generateBullets(p);
    whyBullets.innerHTML = bullets.map(b => `<li>${escapeHtml(b)}</li>`).join('');

    // Show section
    whySection.style.display = 'block';

    // Check if presets available and show sticky CTA
    checkPresetsAndShowCTA();
  }

  async function checkPresetsAndShowCTA() {
    if (!stickyCTA) return;

    try {
      // Get item ID from print settings card
      const printSettingsCard = document.getElementById('print-settings-card');
      if (!printSettingsCard) return;
      
      const itemId = printSettingsCard.getAttribute('data-item-id');
      if (!itemId) return;

      // Check if slice hints are available
      const res = await fetch(`/api/item/${itemId}/slice-hints`);
      const data = await res.json();

      if (data.ok && data.slice_hints && Object.keys(data.slice_hints).length > 0) {
        // Show sticky CTA after a short delay for better UX
        setTimeout(() => {
          stickyCTA.style.display = 'block';
        }, 1500);
      }
    } catch (err) {
      console.debug('Slice hints check failed:', err);
    }
  }

  function generateSummary(score) {
    if (score >= 85) {
      return 'High confidence print — excellent geometry and structure.';
    } else if (score >= 70) {
      return 'Should print well with typical settings.';
    } else if (score >= 50) {
      return 'May require tuning for best results.';
    } else {
      return 'Print with caution — consider reviewing geometry.';
    }
  }

  function generateBullets(printability) {
    const bullets = [];
    
    // Overhang analysis
    const overhang = printability.overhang_percent || 0;
    if (overhang < 10) {
      bullets.push('Low overhangs (supports usually not needed)');
    } else if (overhang < 25) {
      bullets.push('Moderate overhangs (supports may help)');
    } else {
      bullets.push('High overhangs (supports recommended)');
    }

    // Manifold check
    if (printability.manifold === true) {
      bullets.push('Closed mesh (manifold geometry)');
    } else if (printability.manifold === false) {
      bullets.push('Non-manifold geometry (may need repair)');
    }

    // Degenerate faces
    const degenerateFaces = printability.degenerate_faces || 0;
    if (degenerateFaces === 0) {
      bullets.push('Clean mesh (no degenerate faces)');
    } else {
      bullets.push(`Mesh issues detected (${degenerateFaces} degenerate faces)`);
    }

    // Thin walls
    if (printability.thin_walls === 0) {
      bullets.push('No thin walls detected');
    } else if (printability.thin_walls > 0) {
      bullets.push(`Thin walls detected (${printability.thin_walls} areas)`);
    }

    // Small features
    if (printability.small_features === 0) {
      bullets.push('No small features that may be unprintable');
    } else if (printability.small_features > 0) {
      bullets.push(`Small features detected (${printability.small_features} areas)`);
    }

    // Fallback if no bullets
    if (bullets.length === 0) {
      bullets.push('Geometry analyzed successfully');
    }

    return bullets;
  }

  function showNeutralMessage() {
    whySummary.textContent = 'No printability insights available yet.';
    whyBullets.innerHTML = '<li style="list-style:none;">Run analysis to see detailed recommendations.</li>';
    whySection.style.display = 'block';
  }

  function escapeHtml(str) {
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
  }

})();
