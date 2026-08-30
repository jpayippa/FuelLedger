import assert from "node:assert/strict";
import { test } from "node:test";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const { escapeHtml } = require("../../static/escape.js");

test("escapes ampersand", () => {
  assert.equal(escapeHtml("a & b"), "a &amp; b");
});

test("escapes less-than and greater-than", () => {
  assert.equal(escapeHtml("<b>"), "&lt;b&gt;");
});

test("escapes double quote", () => {
  assert.equal(escapeHtml('say "hi"'), "say &quot;hi&quot;");
});

test("escapes single quote", () => {
  assert.equal(escapeHtml("it's"), "it&#39;s");
});

test("escapes all five characters combined", () => {
  assert.equal(escapeHtml(`<a href="x" onclick='y'>&</a>`),
    "&lt;a href=&quot;x&quot; onclick=&#39;y&#39;&gt;&amp;&lt;/a&gt;");
});

test("plain text passes through unchanged", () => {
  assert.equal(escapeHtml("Shell Gas Station"), "Shell Gas Station");
});

test("empty string stays empty", () => {
  assert.equal(escapeHtml(""), "");
});

test("null becomes empty string", () => {
  assert.equal(escapeHtml(null), "");
});

test("undefined becomes empty string", () => {
  assert.equal(escapeHtml(undefined), "");
});

test("numbers are stringified safely", () => {
  assert.equal(escapeHtml(1234), "1234");
});

test("a script-tag payload is neutralized", () => {
  const out = escapeHtml("<script>alert(1)</script>");
  assert.ok(!out.includes("<script>"));
  assert.equal(out, "&lt;script&gt;alert(1)&lt;/script&gt;");
});

test("an attribute-breakout payload is neutralized", () => {
  const out = escapeHtml('" onmouseover="alert(1)');
  assert.ok(!out.includes('"'));
  assert.equal(out, "&quot; onmouseover=&quot;alert(1)");
});
