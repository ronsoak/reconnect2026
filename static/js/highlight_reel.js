(function () {
  var reel = document.querySelector(".highlight-reel");
  if (!reel) return;
  var slides = reel.querySelector(".highlight-reel__slides");
  var controls = reel.querySelector(".highlight-reel__controls");
  var buttons = Array.from(controls.querySelectorAll("button"));
  var reduced = window.matchMedia("(prefers-reduced-motion: reduce)");
  function update() {
    buttons[0].disabled = slides.scrollLeft <= 1;
    buttons[1].disabled = slides.scrollLeft + slides.clientWidth >= slides.scrollWidth - 1;
  }
  buttons.forEach(function (button) {
    button.addEventListener("click", function () {
      slides.scrollBy({
        left: Number(button.dataset.direction) * slides.clientWidth,
        behavior: reduced.matches ? "instant" : "smooth"
      });
    });
  });
  controls.hidden = slides.children.length < 2;
  slides.addEventListener("scroll", update, { passive: true });
  window.addEventListener("resize", update);
  reel.parentElement.addEventListener("widgets:layout", update);
  update();
})();
