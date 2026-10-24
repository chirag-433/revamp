(() => {
  const buttons = document.querySelectorAll('[data-state]');
  const summary = document.querySelector('[data-state-summary]');
  const initial = summary?.textContent;
  buttons.forEach((button) => button.addEventListener('click', () => {
    buttons.forEach((item) => item.setAttribute('aria-pressed', 'false'));
    button.setAttribute('aria-pressed', 'true');
    const state = button.dataset.state;
    const count = button.dataset.count;
    const link = button.dataset.link;
    if (summary) {
      summary.innerHTML = `<strong>${state}</strong><span>${count} case${count === '1' ? '' : 's'} in the current workspace.</span><a href="${link}">Open these cases →</a>`;
    }
  }));
  document.querySelector('[data-reset-state]')?.addEventListener('click', () => {
    buttons.forEach((item) => item.setAttribute('aria-pressed', 'false'));
    if (summary) summary.textContent = initial;
  });
})();
