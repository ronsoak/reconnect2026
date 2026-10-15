(function () {
  var ticker = document.querySelector(".article-ticker");
  if (!ticker) return;
  var track = ticker.querySelector(".article-ticker__track");
  var items = ticker.querySelector(".article-ticker__items");
  var reduced = window.matchMedia("(prefers-reduced-motion: reduce)");
  var copy = items.cloneNode(true);
  copy.setAttribute("aria-hidden", "true");
  copy.classList.add("article-ticker__copy");
  copy.querySelectorAll("a").forEach(function (link) { link.tabIndex = -1; });
  track.appendChild(copy);
  ticker.classList.add("is-enhanced");
  function update() {
    ticker.classList.toggle("is-reduced", reduced.matches);
    track.style.setProperty("--ticker-duration", Math.max(20, items.scrollWidth / 40) + "s");
  }
  reduced.addEventListener("change", update);
  ticker.parentElement.addEventListener("widgets:layout", update);
  if (document.fonts) document.fonts.ready.then(update);
  update();
})();
