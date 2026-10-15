(function () {
  var grid = document.querySelector(".feed-grid");
  if (!grid || !grid.querySelector("[data-feed-widget]")) return;
  grid.classList.add("has-widget-layout");
  var nodes = Array.from(grid.children);
  var pending = false;

  function layout() {
    var columns = Number(getComputedStyle(grid).getPropertyValue("--feed-columns"));
    var occupied = [];
    var floor = 0;
    var lastWidget = null;
    var ordinary = 0;
    var templates = [];
    var end = 0;

    function free(row, column, width, height) {
      for (var y = row; y < row + height; y++) {
        for (var x = column; x < column + width; x++) {
          if (occupied[y] && occupied[y][x]) return false;
        }
      }
      return true;
    }
    nodes.forEach(function (node) {
      var kind = node.dataset.feedWidget;
      var fullWidth = kind === "ticker" || kind === "highlight";
      node.hidden = false;
      var width = fullWidth ? columns : node.classList.contains("feed-card--large") ? 2 : 1;
      var height = !fullWidth && (node.classList.contains("feed-card--large") ||
        node.classList.contains("feed-card--medium")) ? 2 : 1;
      var row = fullWidth ? end : floor;
      var column = 0;
      if (!fullWidth) {
        search: for (;; row++) {
          for (column = 0; column <= columns - width; column++) {
            if (free(row, column, width, height)) break search;
          }
        }
      }
      var completeRows = 0;
      if (kind && lastWidget) {
        for (var r = lastWidget.end; r < row; r++) {
          if (occupied[r] && occupied[r].filter(Boolean).length === columns) completeRows++;
        }
      }
      // Only fully occupied ordinary rows count, not empty cells left by tall cards.
      if (kind && lastWidget && (ordinary - lastWidget.count < 10 || completeRows < 2)) {
        node.hidden = true;
        node.style.removeProperty("grid-row");
        node.style.removeProperty("grid-column");
        return;
      }
      for (var y = row; y < row + height; y++) {
        if (!occupied[y]) occupied[y] = [];
        for (var x = column; x < column + width; x++) occupied[y][x] = true;
        templates[y] = fullWidth ? "auto" : "17rem";
      }
      node.style.gridRow = (row + 1) + " / span " + height;
      node.style.gridColumn = (column + 1) + " / span " + width;
      end = Math.max(end, row + height);
      if (kind) {
        lastWidget = { end: row + height, count: ordinary };
        // Full-width rows are barriers; ordinary cards may still fill beside Newest Additions.
        floor = fullWidth ? end : row;
      } else {
        ordinary++;
      }
    });
    grid.style.gridTemplateRows = templates.join(" ");
    grid.dispatchEvent(new Event("widgets:layout"));
  }

  function schedule() {
    if (pending) return;
    pending = true;
    requestAnimationFrame(function () { pending = false; layout(); });
  }
  window.addEventListener("resize", schedule);
  new MutationObserver(function (changes) {
    if (changes.some(function (change) {
      return nodes.includes(change.target) && change.target.classList.contains("feed-card");
    })) schedule();
  }).observe(grid, { subtree: true, attributes: true, attributeFilter: ["class"] });
  if (document.fonts) document.fonts.ready.then(schedule);
  layout();
})();
