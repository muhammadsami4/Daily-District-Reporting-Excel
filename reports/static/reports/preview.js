// Live column sums and declared-total checks on the preview page.
// This is only a convenience: the server re-validates everything before saving.
(function () {
  function num(el) {
    var s = (el.value || "").trim();
    return s === "" ? null : Number(s);
  }
  function update() {
    document.querySelectorAll('[id^="sum-"]').forEach(function (cell) {
      var code = cell.id.slice(4), sum = 0;
      document.querySelectorAll('.cell-input[data-cat="' + code + '"]').forEach(function (input) {
        var v = num(input);
        if (v !== null && !isNaN(v)) sum += v;
      });
      cell.textContent = sum;
      var declaredEl = document.getElementById("declared-" + code);
      var status = document.getElementById("status-" + code);
      var declared = declaredEl ? num(declaredEl) : null;
      if (declared === null) {
        status.innerHTML = sum === 0 ? '<span class="text-muted">—</span>' : '<span class="badge text-bg-warning">no total</span>';
      } else if (declared === sum) {
        status.innerHTML = '<span class="badge text-bg-success">match</span>';
      } else {
        var diff = sum - declared;
        status.innerHTML = '<span class="badge text-bg-danger">' + (diff > 0 ? "+" : "") + diff + "</span>";
      }
    });
  }
  document.addEventListener("input", function (e) {
    if (e.target.matches(".cell-input, .declared-input")) {
      e.target.classList.remove("is-invalid");
      update();
    }
  });
  update();
})();
