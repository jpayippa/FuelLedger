function escapeHtml(value) {
  if (value === null || value === undefined) return "";
  return String(value).replace(/[&<>"']/g, (c) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
  }[c]));
}

// Browsers ignore this (no `module` global); lets the test suite `require()`
// the exact same function shipped to the browser, rather than a copy of it.
if (typeof module !== "undefined") module.exports = { escapeHtml };
