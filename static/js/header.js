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
})();
