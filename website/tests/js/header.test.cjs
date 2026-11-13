const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const path = require("node:path");

const source = fs.readFileSync(path.join(__dirname, "../../../static/js/header.js"), "utf8");

function render(total, reduced = false) {
  const classes = new Set();
  const frames = new Map();
  const listeners = new Set();
  const formatted = new Intl.NumberFormat("en-US").format(total);
  const animated = { textContent: formatted };
  const final = { textContent: formatted };
  const counter = {
    dataset: { headerCount: String(total) },
    classList: {
      add: value => classes.add(value),
      remove: value => classes.delete(value),
    },
    querySelector: selector => selector.endsWith("animated") ? animated : final,
  };
  const header = {
    getBoundingClientRect: () => ({ height: 100 }),
    querySelector: () => counter,
  };
  let nextFrame = 0;
  vm.runInNewContext(source, {
    document: {
      querySelector: () => header,
      documentElement: { style: { setProperty() {} } },
    },
    window: {
      matchMedia: () => ({
        matches: reduced,
        addEventListener: (_, listener) => listeners.add(listener),
        removeEventListener: (_, listener) => listeners.delete(listener),
      }),
    },
    ResizeObserver: class { observe() {} },
    performance: { now: () => 100 },
    requestAnimationFrame(callback) {
      frames.set(++nextFrame, callback);
      return nextFrame;
    },
    cancelAnimationFrame: id => frames.delete(id),
  });
  return {
    animated, final, classes, frames, listeners,
    tick(elapsed) {
      const callbacks = Array.from(frames.values());
      frames.clear();
      callbacks.forEach(callback => callback(100 + elapsed));
    },
    reduceMotion() {
      for (const listener of listeners) listener({ matches: true });
    },
  };
}

test("count-up keeps the accessible final value and reaches it within 250ms", () => {
  const fixture = render(1234567);
  assert.equal(fixture.animated.textContent, "0");
  assert.ok(fixture.classes.has("is-counting"));
  fixture.tick(125);
  const midpoint = Number(fixture.animated.textContent.replaceAll(",", ""));
  assert.ok(midpoint > 1234567 / 2 && midpoint < 1234567);
  assert.match(fixture.animated.textContent, /^\d{1,3}(,\d{3})+$/);
  assert.equal(fixture.final.textContent, "1,234,567");
  fixture.tick(249);
  assert.ok(fixture.classes.has("is-counting"));
  fixture.tick(250);
  assert.equal(fixture.classes.has("is-counting"), false);
  assert.equal(fixture.final.textContent, "1,234,567");
  assert.equal(fixture.frames.size, 0);
  assert.equal(fixture.listeners.size, 0);
});

test("reduced motion and zero counts keep the server-rendered value without animation", () => {
  for (const [total, reduced] of [[59056, true], [0, false]]) {
    const fixture = render(total, reduced);
    assert.equal(fixture.classes.has("is-counting"), false);
    assert.equal(fixture.animated.textContent, fixture.final.textContent);
    assert.equal(fixture.frames.size, 0);
    assert.equal(fixture.listeners.size, 0);
  }
});

test("enabling reduced motion mid-animation immediately reveals the final count", () => {
  const fixture = render(59056);
  fixture.tick(50);
  fixture.reduceMotion();
  assert.equal(fixture.classes.has("is-counting"), false);
  assert.equal(fixture.final.textContent, "59,056");
  assert.equal(fixture.frames.size, 0);
  assert.equal(fixture.listeners.size, 0);
});

test("a delayed animation frame finishes immediately instead of extending the duration", () => {
  const fixture = render(59056);
  fixture.tick(1000);
  assert.equal(fixture.classes.has("is-counting"), false);
  assert.equal(fixture.final.textContent, "59,056");
  assert.equal(fixture.frames.size, 0);
});
