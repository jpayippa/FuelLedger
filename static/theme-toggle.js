(function () {
  var stored = localStorage.getItem("fuelledger-theme");
  document.documentElement.setAttribute("data-theme", stored || "dark");
})();

function toggleTheme() {
  var current = document.documentElement.getAttribute("data-theme") || "dark";
  var next = current === "dark" ? "light" : "dark";
  document.documentElement.setAttribute("data-theme", next);
  localStorage.setItem("fuelledger-theme", next);
}
