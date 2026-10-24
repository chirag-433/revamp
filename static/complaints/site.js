(() => {
  const body = document.body;
  const menuButton = document.querySelector('[data-nav-toggle]');
  const nav = document.querySelector('[data-main-nav]');
  const progress = document.querySelector('[data-scroll-progress]');
  const backToTop = document.querySelector('[data-back-to-top]');

  const closeMenu = () => {
    body.classList.remove('nav-open');
    menuButton?.setAttribute('aria-expanded', 'false');
  };
  menuButton?.addEventListener('click', () => {
    const isOpen = body.classList.toggle('nav-open');
    menuButton.setAttribute('aria-expanded', String(isOpen));
  });
  nav?.querySelectorAll('a, button').forEach((link) => link.addEventListener('click', closeMenu));
  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape') closeMenu();
  });

  const updateScrollUi = () => {
    const max = document.documentElement.scrollHeight - window.innerHeight;
    const percent = max > 0 ? (window.scrollY / max) * 100 : 0;
    if (progress) progress.style.transform = `scaleX(${percent / 100})`;
    backToTop?.classList.toggle('is-visible', window.scrollY > 520);
  };
  window.addEventListener('scroll', updateScrollUi, {passive: true});
  updateScrollUi();
  backToTop?.addEventListener('click', () => window.scrollTo({top: 0, behavior: 'smooth'}));

  const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  document.querySelectorAll('.workload-card strong, .summary-card strong').forEach((element) => {
    const value = Number(element.textContent.trim().replace(/[^0-9.]/g, ''));
    if (reduceMotion || !Number.isFinite(value) || value === 0) return;
    const duration = 700;
    const start = performance.now();
    const tick = (now) => {
      const progressValue = Math.min((now - start) / duration, 1);
      element.textContent = Math.round(value * (1 - Math.pow(1 - progressValue, 3))).toString().padStart(2, '0');
      if (progressValue < 1) requestAnimationFrame(tick);
    };
    element.textContent = '00';
    requestAnimationFrame(tick);
  });

  if (!reduceMotion && 'IntersectionObserver' in window) {
    const observer = new IntersectionObserver((entries) => entries.forEach((entry) => {
      if (entry.isIntersecting) { entry.target.classList.add('is-revealed'); observer.unobserve(entry.target); }
    }), {threshold: 0.12});
    document.querySelectorAll('.surface, .workload-card, .workflow-step, .overlap-alert-panel').forEach((item) => {
      item.classList.add('reveal-on-scroll'); observer.observe(item);
    });
  }
})();
