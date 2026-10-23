(() => {
  const finePointer = window.matchMedia(
    "(hover: hover) and (pointer: fine) and (prefers-reduced-motion: no-preference)",
  );
  const overlay = document.querySelector(".cursor-overlay");
  if (!finePointer.matches || !overlay) return;

  const label = overlay.querySelector(".cursor-label");
  let frame = 0;
  let pointerX = -100;
  let pointerY = -100;

  document.body.classList.add("has-cursor-overlay");

  document.addEventListener("pointermove", (event) => {
    if (event.pointerType !== "mouse") return;
    pointerX = event.clientX;
    pointerY = event.clientY;
    if (frame) return;
    frame = window.requestAnimationFrame(() => {
      overlay.style.transform = `translate3d(${pointerX - 17}px, ${pointerY - 17}px, 0)`;
      overlay.classList.add("is-visible");
      frame = 0;
    });
  });

  document.addEventListener("pointerover", (event) => {
    if (event.pointerType && event.pointerType !== "mouse") return;
    const target = event.target instanceof Element
      ? event.target.closest("a, button, select, input[type='submit']")
      : null;

    if (!target) {
      overlay.classList.remove("is-active");
      return;
    }

    if (target.matches(".attention-row")) label.textContent = "OPEN CASE";
    else if (target.matches(".intake-button")) label.textContent = "IMPORT DATA";
    else if (target.matches(".case-reference")) label.textContent = "CASE FILE";
    else if (target.closest(".topbar nav")) label.textContent = "NAVIGATE";
    else if (target.matches("select")) label.textContent = "SELECT";
    else label.textContent = "OPEN";

    overlay.classList.add("is-active");
  });

  document.addEventListener("pointerout", (event) => {
    if (event.relatedTarget instanceof Node && document.contains(event.relatedTarget)) return;
    overlay.classList.remove("is-visible", "is-active");
  });

  window.addEventListener("blur", () => overlay.classList.remove("is-visible", "is-active"));
  finePointer.addEventListener("change", (event) => {
    if (!event.matches) {
      document.body.classList.remove("has-cursor-overlay");
      overlay.classList.remove("is-visible", "is-active");
    }
  });
})();
