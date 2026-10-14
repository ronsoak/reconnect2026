(function () {
  var counter = document.querySelector("[data-footer-count]");
  var reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
  if (!counter || !window.IntersectionObserver || !counter.animate) return;

  var observer = new IntersectionObserver(function (entries) {
    if (!entries.some(function (entry) { return entry.isIntersecting; })) return;
    observer.disconnect();
    if (reducedMotion.matches) return;

    var animation = counter.animate(
      [
        { opacity: 0.6, transform: "translateY(6px)" },
        { opacity: 1, transform: "translateY(0)" }
      ],
      { duration: 200, easing: "cubic-bezier(0.23, 1, 0.32, 1)" }
    );
    function onPreferenceChange(event) {
      if (event.matches) animation.finish();
    }
    reducedMotion.addEventListener("change", onPreferenceChange);
    animation.addEventListener("finish", function () {
      reducedMotion.removeEventListener("change", onPreferenceChange);
    }, { once: true });
  });
  observer.observe(counter);
})();
