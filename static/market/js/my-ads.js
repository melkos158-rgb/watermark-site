// Simple carousel behavior for my-ads page.
// Progressive enhancement: server renders initial order; JS attaches handlers.
document.addEventListener('DOMContentLoaded', function(){
  const carousel = document.getElementById('myAdsCarousel');
  if (!carousel) return;

  const items = Array.from(carousel.querySelectorAll('.carousel-item'));
  if (items.length === 0) return;

  let activeIndex = 0;

  // If >=3 items, set center to index 1 initially to match mockup
  if (items.length >= 3) activeIndex = 1;

  function applyState() {
    items.forEach((it, idx) => {
      it.classList.remove('active','prev','next');
      if (idx === activeIndex) it.classList.add('active');
      else if (idx === (activeIndex - 1 + items.length) % items.length) it.classList.add('prev');
      else if (idx === (activeIndex + 1) % items.length) it.classList.add('next');
    });
  }

  applyState();

  const leftBtn = document.querySelector('.my-ads-arrow.left');
  const rightBtn = document.querySelector('.my-ads-arrow.right');

  function rotateLeft(){
    activeIndex = (activeIndex - 1 + items.length) % items.length;
    applyState();
    items[activeIndex].scrollIntoView({inline:'center', behavior:'smooth'});
  }
  function rotateRight(){
    activeIndex = (activeIndex + 1) % items.length;
    applyState();
    items[activeIndex].scrollIntoView({inline:'center', behavior:'smooth'});
  }

  if (leftBtn) leftBtn.addEventListener('click', rotateLeft);
  if (rightBtn) rightBtn.addEventListener('click', rotateRight);

  // Keyboard navigation
  carousel.setAttribute('tabindex', '0');
  carousel.addEventListener('keydown', (e) => {
    if (e.key === 'ArrowLeft') rotateLeft();
    if (e.key === 'ArrowRight') rotateRight();
  });
});
