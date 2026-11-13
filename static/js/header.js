// Keep anchor and focus scrolling clear of the responsive sticky header.
(function () {
  const header = document.querySelector(".site-header");
  if (!header) return;

  function updateHeight() {
    document.documentElement.style.setProperty(
      "--site-header-height",
      `${header.getBoundingClientRect().height}px`
    );
  }

  updateHeight();
  new ResizeObserver(updateHeight).observe(header);

  const counter = header.querySelector("[data-header-count]");
  if (!counter) return;

  const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
  const total = Number(counter.dataset.headerCount);
  if (reducedMotion.matches || total === 0) return;

  const animated = counter.querySelector(".site-header__count-animated");
  const formatter = new Intl.NumberFormat("en-US");
  const started = performance.now();
  const duration = 250;
  let frame;

  function finish() {
    cancelAnimationFrame(frame);
    counter.classList.remove("is-counting");
    reducedMotion.removeEventListener("change", onPreferenceChange);
  }

  function onPreferenceChange(event) {
    if (event.matches) finish();
  }

  function updateCount(now) {
    const progress = Math.min((now - started) / duration, 1);
    if (progress === 1) {
      finish();
      return;
    }
    // easeOutCubic: quick initial progress with a gentle finish.
    const eased = 1 - Math.pow(1 - progress, 3);
    animated.textContent = formatter.format(Math.floor(total * eased));
    frame = requestAnimationFrame(updateCount);
  }

  animated.textContent = "0";
  counter.classList.add("is-counting");
  reducedMotion.addEventListener("change", onPreferenceChange);
  frame = requestAnimationFrame(updateCount);
})();
