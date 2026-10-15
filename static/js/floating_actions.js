// Floating feed actions: the back-to-top button (all feeds) and the refresh
// button (Dynamic only). Both live in templates/components/floating_actions.html.
//
// - The group is lifted by however much of the footer is visible so it never
//   covers the footer.
// - The back-to-top button appears once the reader has scrolled past the first
//   screen and returns them to the top, smoothly unless reduced motion is set.
// - Near the bottom of the Dynamic feed the refresh button grows and moves to
//   the centre to prompt another batch.
(function () {
  var group = document.querySelector("[data-floating-actions]");
  if (!group) return;

  var footer = document.querySelector(".site-footer");
  var topButton = group.querySelector("[data-scroll-top]");
  var hasRefresh = Boolean(group.querySelector(".refresh-button"));
  var reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");

  // Distance from the bottom, in pixels, that counts as "at the bottom"
  var END_THRESHOLD = 200;

  function update() {
    var scrolled = window.scrollY + window.innerHeight;
    var atEnd = scrolled >= document.documentElement.scrollHeight - END_THRESHOLD;
    group.classList.toggle("is-at-end", hasRefresh && atEnd);

    // Show back-to-top once the first screen has scrolled away
    if (topButton) {
      topButton.classList.toggle("is-visible", window.scrollY > window.innerHeight * 0.75);
    }

    var lift = 0;
    if (footer) {
      lift = Math.max(0, window.innerHeight - footer.getBoundingClientRect().top);
    }
    group.style.setProperty("--floating-lift", lift + "px");
  }

  if (topButton) {
    topButton.addEventListener("click", function () {
      window.scrollTo({ top: 0, behavior: reducedMotion.matches ? "auto" : "smooth" });
      // Keyboard and screen-reader users continue from the top of the page
      var start = document.querySelector(".site-brand");
      if (start) start.focus({ preventScroll: true });
    });
  }

  window.addEventListener("scroll", update, { passive: true });
  window.addEventListener("resize", update);
  update();
})();
