(function () {
  var ticker = document.querySelector(".article-ticker");
  var grid = document.querySelector(".feed-grid");
  if (!ticker || !grid) return;
  var cards = Array.from(grid.children);
  var target = Number(ticker.dataset.tickerTarget);
  var track = ticker.querySelector(".article-ticker__track");
  var items = ticker.querySelector(".article-ticker__items");
  var reduced = window.matchMedia("(prefers-reduced-motion: reduce)");
  var pending = false;

  function placeTicker() {
    // Measure the unbroken grid, including current image-failure size changes.
    ticker.remove();
    grid.style.removeProperty("grid-template-rows");
    var style = getComputedStyle(grid);
    var rowHeight = parseFloat(style.gridAutoRows);
    var gap = parseFloat(style.rowGap);
    var columns = style.gridTemplateColumns.split(" ").length;
    var top = grid.getBoundingClientRect().top;
    var columnWidth = (grid.clientWidth + gap) / columns;
    var left = grid.getBoundingClientRect().left;
    var cells = cards.map(function (card) {
      var rect = card.getBoundingClientRect();
      return {
        card: card,
        start: Math.round((rect.top - top) / (rowHeight + gap)),
        end: Math.round((rect.bottom - top + gap) / (rowHeight + gap)),
        column: Math.round((rect.left - left) / columnWidth),
        width: Math.round((rect.width + gap) / columnWidth)
      };
    });
    var rows = Math.max.apply(null, cells.map(function (cell) { return cell.end; }));
    var desired = Math.max(1, Math.min(rows - 1, Math.round(target * rows)));
    var boundaries = [];
    for (var row = 1; row < rows; row++) {
      var crossing = cells.some(function (cell) { return cell.start < row && cell.end > row; });
      var filled = new Set();
      cells.forEach(function (cell) {
        if (cell.end === row) {
          for (var column = cell.column; column < cell.column + cell.width; column++) filled.add(column);
        }
      });
      if (!crossing && filled.size === columns) boundaries.push(row);
    }
    var boundary = boundaries.length ? boundaries.reduce(function (best, row) {
      return Math.abs(row - desired) < Math.abs(best - desired) ? row : best;
    }) : Math.min(rows, Math.max(2, desired));
    // An explicitly occupied full-width row prevents auto-placed cards spanning it,
    // even if no natural boundary exists. Only this row gets the ticker's own height.
    grid.style.gridTemplateRows = "repeat(" + boundary + ", " + rowHeight + "px) auto";
    ticker.style.gridRow = String(boundary + 1);
    var next = cells.find(function (cell) { return cell.start >= boundary; });
    grid.insertBefore(ticker, next ? next.card : null);
    track.style.setProperty("--ticker-duration", Math.max(20, items.scrollWidth / 40) + "s");
  }

  function schedulePlacement() {
    if (pending) return;
    pending = true;
    requestAnimationFrame(function () {
      pending = false;
      placeTicker();
    });
  }

  var copy = items.cloneNode(true);
  copy.setAttribute("aria-hidden", "true");
  copy.classList.add("article-ticker__copy");
  copy.querySelectorAll("a").forEach(function (link) { link.tabIndex = -1; });
  track.appendChild(copy);
  ticker.classList.add("is-enhanced");
  function motionPreference() {
    ticker.classList.toggle("is-reduced", reduced.matches);
    schedulePlacement();
  }
  reduced.addEventListener("change", motionPreference);
  window.addEventListener("resize", schedulePlacement);
  // Broken images can change large/medium cards to small after initial placement.
  new MutationObserver(function (changes) {
    if (changes.some(function (change) { return cards.includes(change.target); })) schedulePlacement();
  }).observe(grid, {
    subtree: true, attributes: true, attributeFilter: ["class"]
  });
  if (document.fonts) document.fonts.ready.then(schedulePlacement);
  motionPreference();
  placeTicker();
})();
