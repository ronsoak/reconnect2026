const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const path = require("node:path");

const source = fs.readFileSync(path.join(__dirname, "../../../static/js/feed_widgets.js"), "utf8");

function render(columns, sizes, widgets) {
  const nodes = [];
  let onResize;
  function node(size, kind, advert = false) {
    const classes = new Set(["feed-card", `feed-card--${size}`]);
    if (advert) classes.add("feed-card--advert");
    return {
      dataset: kind ? { feedWidget: kind } : {},
      classList: { contains: value => classes.has(value), add: value => classes.add(value) },
      style: { removeProperty() {} },
      hidden: false,
    };
  }
  sizes.forEach((size, index) => {
    nodes.push(node(size, null, index === 7));
    if (widgets[index + 1]) nodes.push(node("medium", widgets[index + 1]));
  });
  const originals = nodes.filter(n => !n.dataset.feedWidget);
  const grid = {
    children: nodes.slice(), classList: { add() {} }, style: {},
    querySelector: () => true, dispatchEvent() {},
    insertBefore(n, next) {
      this.children.splice(this.children.indexOf(n), 1);
      this.children.splice(next ? this.children.indexOf(next) : this.children.length, 0, n);
    },
  };
  vm.runInNewContext(source, {
    document: { querySelector: () => grid },
    window: { addEventListener(name, handler) { if (name === "resize") onResize = handler; } }, Event: class {},
    MutationObserver: class { observe() {} },
    getComputedStyle: () => ({ getPropertyValue: () => columns }),
    requestAnimationFrame: callback => callback(),
  });
  assert.deepEqual(grid.children.filter(n => !n.dataset.feedWidget), originals);
  assert.equal(originals[0].dataset.widgetSmall, undefined);
  assert.equal(originals[7].dataset.widgetSmall, undefined);
  return { grid, originals, resize(value) { columns = value; onResize(); } };
}

function verify(grid, columns) {
  const occupied = [];
  let segment = 0;
  let count = 0;
  let last = null;
  for (const n of grid.children.filter(n => !n.hidden)) {
    const [row, height] = n.style.gridRow.match(/\d+/g).map(Number);
    const [column, width] = n.style.gridColumn.match(/\d+/g).map(Number);
    const kind = n.dataset.feedWidget;
    if (kind === "ticker" || kind === "highlight") {
      for (let r = segment; r < row - 1; r++) {
        assert.equal(occupied[r]?.filter(Boolean).length, columns, "no empty cell above a break");
      }
      segment = row;
    }
    if (kind) {
      if (last) {
        assert.ok(count - last.count >= 10);
        let complete = 0;
        for (let r = last.end; r < row - 1; r++) {
          if (occupied[r]?.filter(Boolean).length === columns) complete++;
        }
        assert.ok(complete >= 2);
      }
      last = { count, end: row - 1 + height };
    } else count++;
    for (let r = row - 1; r < row - 1 + height; r++) {
      occupied[r] ??= [];
      for (let c = column - 1; c < column - 1 + width; c++) {
        assert.ok(!occupied[r][c], "cards never overlap");
        occupied[r][c] = true;
      }
    }
  }
}

test("full-width widgets use completely filled breaks across card mixes and widths", () => {
  let visible = 0;
  for (const columns of [2, 3, 4]) {
    for (let seed = 0; seed < 30; seed++) {
      const sizes = Array.from({ length: 100 }, (_, i) =>
        i === 0 || (i + seed) % 11 === 0 ? "large" : (i + seed) % 3 === 0 ? "medium" : "small");
      const { grid } = render(columns, sizes, { 20: "newest", 45: "ticker", 75: "highlight" });
      verify(grid, columns);
      visible += grid.children.filter(n => !n.hidden && ["ticker", "highlight"].includes(n.dataset.feedWidget)).length;
    }
  }
  assert.ok(visible >= 150, `most full-width widgets remain visible: ${visible}/180`);
});

test("a natural later break wins without resizing articles", () => {
  const { grid, originals } = render(4, Array(40).fill("small"), { 10: "ticker", 30: "highlight" });
  verify(grid, 4);
  assert.ok(originals.every(n => n.dataset.widgetSmall === undefined));
  assert.equal(grid.children.indexOf(grid.children.find(n => n.dataset.feedWidget === "ticker")), 12);
});

test("selective resizing closes a break while adverts and first card keep their size", () => {
  const { grid, originals } = render(4,
    ["large", ...Array(11).fill("small"), "medium"], { 13: "ticker" });
  verify(grid, 4);
  assert.equal(originals[12].dataset.widgetSmall, "");
  assert.ok(!grid.children.find(n => n.dataset.feedWidget).hidden);
});

test("resize and image-failure size changes recalculate from original cards", () => {
  const fixture = render(4,
    Array.from({ length: 100 }, (_, i) => i % 5 ? "small" : "large"),
    { 20: "newest", 45: "ticker", 75: "highlight" });
  for (const columns of [3, 2, 4]) {
    fixture.resize(columns);
    verify(fixture.grid, columns);
  }
  fixture.originals.forEach(n => {
    n.classList.contains = value => value === "feed-card" || value === "feed-card--small";
  });
  fixture.resize(4);
  verify(fixture.grid, 4);
  assert.ok(fixture.originals.every(n => n.dataset.widgetSmall === undefined));
});

test("an impossible short boundary omits the widget without losing cards", () => {
  const { grid, originals } = render(4, Array(10).fill("small"), { 10: "ticker" });
  assert.ok(grid.children.find(n => n.dataset.feedWidget).hidden);
  assert.equal(originals.filter(n => !n.hidden).length, 10);
  verify(grid, 4);
});
