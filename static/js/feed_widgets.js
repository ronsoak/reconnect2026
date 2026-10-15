(function () {
  var grid = document.querySelector(".feed-grid");
  if (!grid || !grid.querySelector("[data-feed-widget]")) return;
  grid.classList.add("has-widget-layout");
  var nodes = Array.from(grid.children);
  var pending = false;

  function layout() {
    var columns = Number(getComputedStyle(grid).getPropertyValue("--feed-columns"));
    var sequence = nodes.slice();
    var shrunk = new Set();
    var omitted = new Set();

    // Trial layouts contain no DOM writes. Prefer a later natural boundary over resizing.
    nodes.filter(function (node) {
      return node.dataset.feedWidget === "ticker" || node.dataset.feedWidget === "highlight";
    }).forEach(function (widget) {
      var start = sequence.indexOf(widget);
      sequence.splice(start, 1);
      var limit = start;
      while (limit < sequence.length && !sequence[limit].dataset.feedWidget) limit++;
      var chosen = -1;
      for (var index = start; index <= limit; index++) {
        var trial = pack(sequence.slice(0, index), shrunk);
        if (trial.clean && trial.allowsWidget) {
          chosen = index;
          break;
        }
      }
      if (chosen < 0) {
        // Search the nearest eight eligible cards, fewest size changes first.
        var segment = 0;
        for (var before = 0; before < start; before++) {
          if (["ticker", "highlight"].includes(sequence[before].dataset.feedWidget)) segment = before + 1;
        }
        var candidates = sequence.slice(segment, limit).filter(function (node) {
          return !node.dataset.feedWidget && node !== nodes[0] &&
            !node.classList.contains("feed-card--advert") &&
            !shrunk.has(node) && (node.classList.contains("feed-card--large") ||
              node.classList.contains("feed-card--medium"));
        }).slice(-8);
        var masks = Array.from({ length: Math.pow(2, candidates.length) - 1 }, function (_, i) {
          return i + 1;
        }).sort(function (a, b) {
          return a.toString(2).replace(/0/g, "").length - b.toString(2).replace(/0/g, "").length;
        });
        for (var m = 0; m < masks.length && chosen < 0; m++) {
          var resized = new Set(shrunk);
          candidates.forEach(function (node, bit) {
            if (masks[m] & (1 << bit)) resized.add(node);
          });
          var fallback = pack(sequence.slice(0, limit), resized);
          if (fallback.clean && fallback.allowsWidget) {
            chosen = limit;
            shrunk = resized;
          }
        }
      }
      if (chosen < 0) {
        omitted.add(widget);
      } else {
        sequence.splice(chosen, 0, widget);
      }
    });

    var result = pack(sequence, shrunk);
    nodes.forEach(function (node) {
      node.hidden = omitted.has(node) || !result.placements.has(node);
      if (shrunk.has(node)) node.dataset.widgetSmall = "";
      else delete node.dataset.widgetSmall;
      var position = result.placements.get(node);
      if (position) {
        node.style.gridRow = (position.row + 1) + " / span " + position.height;
        node.style.gridColumn = (position.column + 1) + " / span " + position.width;
      } else {
        node.style.removeProperty("grid-row");
        node.style.removeProperty("grid-column");
      }
    });
    // Move only widget nodes, preserving ordinary article/adverts and keyboard order.
    sequence.forEach(function (node, index) {
      if (node.dataset.feedWidget) {
        grid.insertBefore(node, sequence.slice(index + 1).find(function (next) {
          return !next.dataset.feedWidget;
        }) || null);
      }
    });
    grid.style.gridTemplateRows = result.templates.join(" ");
    grid.dispatchEvent(new Event("widgets:layout"));

    function pack(items, small) {
    var occupied = [];
    var floor = 0;
    var segmentStart = 0;
    var lastWidget = null;
    var ordinary = 0;
    var templates = [];
    var end = 0;
    var placements = new Map();

    function free(row, column, width, height) {
      for (var y = row; y < row + height; y++) {
        for (var x = column; x < column + width; x++) {
          if (occupied[y] && occupied[y][x]) return false;
        }
      }
      return true;
    }
    function allows(row) {
      if (!lastWidget) return true;
      var complete = 0;
      for (var r = lastWidget.end; r < row; r++) {
        if (occupied[r] && occupied[r].filter(Boolean).length === columns) complete++;
      }
      return ordinary - lastWidget.count >= 10 && complete >= 2;
    }
    function clean() {
      if (end === segmentStart) return false;
      for (var row = segmentStart; row < end; row++) {
        if (!occupied[row] || occupied[row].filter(Boolean).length !== columns) return false;
      }
      return true;
    }
    items.forEach(function (node) {
      var kind = node.dataset.feedWidget;
      var fullWidth = kind === "ticker" || kind === "highlight";
      // On the two-column phone grid Newest Sites spans the row, one row tall.
      var wideNewest = kind === "newest" && columns <= 2;
      var width = fullWidth || wideNewest ? columns :
        !small.has(node) && node.classList.contains("feed-card--large") ? 2 : 1;
      var height = !fullWidth && !wideNewest && !small.has(node) && (node.classList.contains("feed-card--large") ||
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
      if (kind && (!allows(row) || (fullWidth && !clean()))) return;
      for (var y = row; y < row + height; y++) {
        if (!occupied[y]) occupied[y] = [];
        for (var x = column; x < column + width; x++) occupied[y][x] = true;
        templates[y] = fullWidth ? "auto" : "17rem";
      }
      placements.set(node, { row: row, column: column, height: height, width: width });
      end = Math.max(end, row + height);
      if (kind) {
        lastWidget = { end: row + height, count: ordinary };
        // Full-width rows are barriers; ordinary cards may still fill beside Newest Sites.
        if (fullWidth) floor = end;
        if (fullWidth) segmentStart = end;
      } else {
        ordinary++;
      }
    });
    return { placements: placements, templates: templates, clean: clean(), allowsWidget: allows(end) };
    }
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
