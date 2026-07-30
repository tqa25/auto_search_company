import assert from "node:assert/strict";

const element = () => ({
  innerHTML: "",
  textContent: "",
  className: "",
  style: {},
  dataset: {},
  value: "",
  checked: false,
  addEventListener() {},
  querySelectorAll() { return []; },
  querySelector() { return element(); },
  classList: { toggle() {} },
});

globalThis.window = {
  lucide: { createIcons() {} },
  addEventListener() {},
};
globalThis.document = {
  body: { dataset: { theme: "dark" } },
  getElementById() { return element(); },
  querySelectorAll() { return []; },
  querySelector() { return element(); },
};
globalThis.location = { hash: "#/dashboard", protocol: "http:", host: "localhost" };
globalThis.fetch = async () => ({ ok: true, json: async () => ({ stats: {}, quota: {}, logs: [] }) });
globalThis.alert = () => {};
globalThis.setInterval = () => 0;
globalThis.setTimeout = () => 0;
globalThis.clearTimeout = () => {};

const RealDate = Date;
class FixedDate extends RealDate {
  constructor(...args) {
    super(...(args.length ? args : ["2026-06-24T20:00:00Z"]));
  }
  static now() {
    return new RealDate("2026-06-24T20:00:00Z").getTime();
  }
}
globalThis.Date = FixedDate;

const {
  formatDashboardTimestamp,
  isValidDomain,
  localDate,
  parseDomainList,
  parseKnownSourceRows,
  parseScoreRows,
} = await import("../dashboard/frontend/assets/app.js");

assert.equal(isValidDomain("example.com"), true);
assert.equal(isValidDomain("sub.example.co"), true);
assert.equal(isValidDomain("not a domain"), false);
assert.equal(isValidDomain("-bad.com"), false);
assert.equal(isValidDomain("bad-.com"), false);

assert.equal(localDate(0), "2026-06-25");
assert.equal(localDate(-1), "2026-06-24");
assert.equal(formatDashboardTimestamp("2026-06-25 23:30:00"), "2026-06-25 23:30:00");
assert.equal(formatDashboardTimestamp("2026-06-25T16:30:00Z"), "2026-06-25 23:30:00");

assert.deepEqual(parseDomainList([" Example.com ", "example.com", "news.vn"], "Skip Domains"), ["example.com", "news.vn"]);
assert.throws(() => parseDomainList(["bad domain"], "Blacklist"), /Blacklist item 1/);

assert.deepEqual(
  parseScoreRows([{ key: "official", score: "15" }, { key: "social", score: "-100" }], "Domain Scores"),
  { official: 15, social: -100 },
);
assert.throws(() => parseScoreRows([{ key: "official", score: "nope" }], "Domain Scores"), /numeric score/);

assert.deepEqual(
  parseKnownSourceRows([{ domain: "Masothue.com", sourceType: "masothue", scoreCategory: "legal" }]),
  { "masothue.com": ["masothue", "legal"] },
);
assert.throws(() => parseKnownSourceRows([{ domain: "example.com", sourceType: "", scoreCategory: "legal" }]), /source type/);
assert.throws(() => parseKnownSourceRows([{ domain: "example.com", sourceType: "source", scoreCategory: "" }]), /score category/);

console.log("settings serializer tests passed");
