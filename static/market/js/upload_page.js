// upload_page.js
// Handles redirect after successful upload on /market/upload

document.addEventListener('DOMContentLoaded', function() {
  // Only run on the dedicated upload page
  const isUploadPage = document.body.classList.contains('market-page-upload');
  if (!isUploadPage) return;

  // Patch the upload form submit to redirect after upload
  const form = document.getElementById('upload-form');
  if (!form) return;

  // Listen for a custom event from upload_manager.js or patch the logic here
  form.addEventListener('upload:success', function(e) {
    const itemId = e.detail && e.detail.item_id;
    if (itemId) {
      window.location.href = `/market/edit/${itemId}`;
    }
  });

  // Fallback: monkey-patch uploadManager to fire the event
  if (window.uploadManager) {
    const origComplete = window.uploadManager.completeItem.bind(window.uploadManager);
    window.uploadManager.completeItem = async function(itemId) {
      const data = await origComplete(itemId);
      // Fire event for redirect
      const event = new CustomEvent('upload:success', { detail: { item_id: itemId } });
      form.dispatchEvent(event);
      return data;
    };
  }
});
