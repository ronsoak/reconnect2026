const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const path = require("node:path");

const source = fs.readFileSync(path.join(__dirname, "../../../static/js/theme.js"), "utf8");

function load({ stored = null, deviceDark = false, storageThrows = false } = {}) {
  const store = new Map(stored ? [["color-scheme", stored]] : []);
  const mediaListeners = [];
  const windowListeners = {};
  const media = {
    matches: deviceDark,
    addEventListener: (_, listener) => mediaListeners.push(listener),
  };
  const inputs = ["auto", "light", "dark"].map(value => ({ value, checked: false }));
  let changeListener;
  const control = {
    hidden: true,
    querySelectorAll: () => inputs,
    addEventListener: (_, listener) => { changeListener = listener; },
  };
  const autoState = { textContent: "" };
  const schemeMeta = { content: "light dark" };
  const themeColorMeta = { content: "#f5f6f2" };
  const root = { dataset: {} };
  const selectors = {
    'meta[name="color-scheme"]': schemeMeta,
    'meta[name="theme-color"]': themeColorMeta,
    "[data-theme-switch]": control,
    "[data-theme-auto-state]": autoState,
  };
  const localStorage = {
    getItem: key => { if (storageThrows) throw new Error("blocked"); return store.has(key) ? store.get(key) : null; },
    setItem: (key, value) => { if (storageThrows) throw new Error("blocked"); store.set(key, value); },
    removeItem: key => { if (storageThrows) throw new Error("blocked"); store.delete(key); },
  };
  const window = {
    localStorage,
    matchMedia: () => media,
    getComputedStyle: () => ({ backgroundColor: root.dataset.theme === "dark" ? "rgb(26, 23, 24)" : "rgb(245, 246, 242)" }),
    addEventListener: (type, listener) => { windowListeners[type] = listener; },
  };
  vm.runInNewContext(source, {
    window,
    document: { documentElement: root, body: {}, querySelector: selector => selectors[selector] || null },
  });
  return {
    store, root, control, inputs, autoState, schemeMeta, themeColorMeta,
    choose: value => changeListener({ target: { value } }),
    deviceChanges: dark => { media.matches = dark; mediaListeners.forEach(listener => listener()); },
    otherTabSaves: value => {
      if (value === null) store.delete("color-scheme"); else store.set("color-scheme", value);
      windowListeners.storage({ key: "color-scheme" });
    },
  };
}

const checked = page => page.inputs.find(input => input.checked).value;

test("defaults to Auto and reports the device scheme", () => {
  const page = load({ deviceDark: true });
  assert.equal(page.control.hidden, false);
  assert.equal(checked(page), "auto");
  assert.equal(page.root.dataset.theme, undefined);
  assert.equal(page.schemeMeta.content, "light dark");
  assert.equal(page.autoState.textContent, " (dark)");
});

test("restores a saved choice", () => {
  const page = load({ stored: "dark" });
  assert.equal(checked(page), "dark");
  assert.equal(page.root.dataset.theme, "dark");
  assert.equal(page.schemeMeta.content, "dark");
  assert.equal(page.themeColorMeta.content, "rgb(26, 23, 24)");
});

test("ignores unexpected stored values", () => {
  const page = load({ stored: "purple" });
  assert.equal(checked(page), "auto");
  assert.equal(page.root.dataset.theme, undefined);
});

test("saves Light or Dark and clears the value for Auto", () => {
  const page = load();
  page.choose("light");
  assert.equal(page.store.get("color-scheme"), "light");
  assert.equal(page.root.dataset.theme, "light");
  page.choose("auto");
  assert.equal(page.store.has("color-scheme"), false);
  assert.equal(page.root.dataset.theme, undefined);
  assert.equal(page.schemeMeta.content, "light dark");
});

test("a device change updates the Auto hint without overriding a manual choice", () => {
  const page = load({ stored: "light" });
  page.deviceChanges(true);
  assert.equal(page.autoState.textContent, " (dark)");
  assert.equal(page.root.dataset.theme, "light");
  assert.equal(page.store.get("color-scheme"), "light");
});

test("follows a choice made in another tab", () => {
  const page = load();
  page.otherTabSaves("dark");
  assert.equal(page.root.dataset.theme, "dark");
  assert.equal(checked(page), "dark");
  page.otherTabSaves(null);
  assert.equal(page.root.dataset.theme, undefined);
});

test("still switches for the current page when storage is blocked", () => {
  const page = load({ storageThrows: true });
  page.choose("dark");
  assert.equal(page.root.dataset.theme, "dark");
  page.deviceChanges(false);
  assert.equal(checked(page), "dark");
});
