const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { JSDOM } = require("jsdom");

const pages = process.argv[2];
const manifest = JSON.parse(fs.readFileSync(path.join(pages, "manifest.json")));
const enhancement = fs.readFileSync(
  "src/uk_parl_written_questions/static/performance/table.js", "utf8"
);
const library = fs.readFileSync(require.resolve("datatables.net"), "utf8");

function openPage(filename, url) {
  return new JSDOM(fs.readFileSync(path.join(pages, filename), "utf8"), {
    url: `https://example.test${url}`,
    runScripts: "outside-only",
    pretendToBeVisual: true
  });
}

function rows(table) {
  return Array.from(table.querySelectorAll("tbody tr"))
    .map(row => Array.from(row.cells).map(cell => cell.textContent.trim()));
}

function tableRows(document) {
  return Array.from(document.querySelectorAll(".performance-table"))
    .map(table => rows(table));
}

function enhance(window) {
  window.alert = message => assert.fail(message);
  window.eval(library);
  assert.equal(window.DataTable.version, "3.0.4");
  window.eval(enhancement);
}

const expected = new Map();
for (const [url, filename] of Object.entries(manifest)) {
  const dom = openPage(filename, url);
  expected.set(url, tableRows(dom.window.document));
  dom.window.close();
}

// Both periods start in their static order; sorts remain local to each table.
const initialPages = [
  "/model/performance/",
  "/model/performance/period/90/"
];
for (const url of initialPages) {
  const dom = openPage(manifest[url], url);
  const { window } = dom;
  const { document } = window;
  assert.ok(document.querySelector('script[src*="dt-3.0.4"]'));
  enhance(window);
  assert.equal(document.querySelectorAll("button[data-sort]:disabled").length, 0);
  assert.deepEqual(tableRows(document), expected.get(url), `Initial order: ${url}`);
  const tables = Array.from(document.querySelectorAll(".performance-table"));
  assert.deepEqual(tables.map(table => table.dataset.questionType), ["priority", "ordinary"]);

  // Alternate tables so every sort must preserve the other table's live state.
  for (let column = 0; column < 7; column++) {
    for (const table of tables) {
      const link = table.querySelectorAll("button[data-sort]")[column];
      const otherTable = tables.find(other => other !== table);
      const otherRows = rows(otherTable);
      const total = table.querySelector(".performance-total").textContent;
      for (let click = 0; click < 2; click++) {
        const originalUrl = window.location.href;
        const direction = link.dataset.direction;
        link.click();
        assert.equal(window.location.href, originalUrl, "Sorting must not change the URL");
        const displayed = Array.from(table.querySelectorAll("tbody tr"));
        const values = displayed.map(row => Number(row.cells[column].dataset.order ?? row.cells[column].textContent));
        assert.deepEqual(values, [...values].sort((a, b) => direction === "asc" ? a - b : b - a));
        if (column !== 0) {
          for (let i = 1; i < displayed.length; i++) {
            if (values[i] === values[i - 1]) {
              assert.ok(Number(displayed[i - 1].cells[0].dataset.order) < Number(displayed[i].cells[0].dataset.order));
            }
          }
        }
        assert.deepEqual(rows(otherTable), otherRows, "Sorting must not change the other table");
        assert.equal(table.querySelector(".performance-total").textContent, total);
        const sorted = table.querySelectorAll("[aria-sort]");
        assert.equal(sorted.length, 1);
        assert.equal(sorted[0], link.closest("th"));
        assert.equal(sorted[0].getAttribute("aria-sort"),
          direction === "asc" ? "ascending" : "descending");
        assert.ok(document.getElementById(`${table.dataset.questionType}-sort-status`)
          .textContent.includes(link.dataset.label));
        for (const filter of document.querySelectorAll("a[data-period]")) {
          const target = new URL(filter.href).pathname;
          assert.ok(expected.has(target), `Period must resolve: ${target}`);
          assert.equal(target, filter.dataset.period === "30"
            ? "/model/performance/" : "/model/performance/period/90/");
        }
      }
    }
  }
  // Each search is confined to its own table.
  const otherRows = rows(tables[1]);
  new window.DataTable(tables[0]).search("Zulu").draw();
  assert.equal(tables[0].querySelectorAll("tbody th").length, 1);
  assert.deepEqual(rows(tables[1]), otherRows);
  window.close();
}

const defaultUrl = "/model/performance/";
const fallback = openPage(manifest[defaultUrl], defaultUrl);
fallback.window.eval(enhancement);
assert.deepEqual(tableRows(fallback.window.document), expected.get(defaultUrl));
for (const link of fallback.window.document.querySelectorAll("a[data-period]")) {
  const target = new URL(link.href);
  assert.ok(expected.has(target.pathname));
  if (target.hash) assert.ok(fallback.window.document.querySelector(target.hash));
}
assert.equal(fallback.window.document.querySelectorAll("button[data-sort]:disabled").length, 14);
fallback.window.close();

const empty = openPage("empty.html", defaultUrl);
enhance(empty.window);
for (const table of empty.window.document.querySelectorAll(".performance-table")) {
  assert.equal(table.querySelectorAll("tbody th").length, 0);
  table.querySelector('button[data-sort="on_time_rate"]').click();
  assert.equal(empty.window.location.pathname, defaultUrl);
  assert.equal(empty.window.location.hash, "");
}
empty.window.close();
console.log(`Verified independent tables against ${expected.size} static states, fallback and empty data.`);
