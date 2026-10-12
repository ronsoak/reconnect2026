// Floating refresh button (dynamic feed only).
// When the reader scrolls to the bottom of the page the button grows and moves
// to the centre to prompt them to load another batch.
(function () {
  var button = document.querySelector(".refresh-button");
  if (!button) return;

  var footer = document.querySelector(".site-footer");

  // Distance from the bottom, in pixels, that counts as "at the bottom"
  var THRESHOLD = 200;

  function update() {
    var scrolled = window.scrollY + window.innerHeight;
    var atEnd = scrolled >= document.documentElement.scrollHeight - THRESHOLD;
    button.classList.toggle("is-at-end", atEnd);

    // Lift the button by however much of the footer is visible so it never overlaps it
    var lift = 0;
    if (footer) {
      lift = Math.max(0, window.innerHeight - footer.getBoundingClientRect().top);
    }
    button.style.setProperty("--refresh-lift", lift + "px");
  }

  window.addEventListener("scroll", update, { passive: true });
  window.addEventListener("resize", update);
  update();
})();
