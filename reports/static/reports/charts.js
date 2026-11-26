// Renders every <canvas data-source="<json_script id>" data-type="line|bar|stacked">.
(function () {
  var palette = ["#2e7d32", "#1565c0", "#6a1b9a", "#ef6c00", "#00838f", "#c62828"];
  document.querySelectorAll("canvas[data-source]").forEach(function (canvas) {
    var holder = document.getElementById(canvas.dataset.source);
    if (!holder) return;
    var data = JSON.parse(holder.textContent);
    var type = canvas.dataset.type;
    var datasets = data.datasets.map(function (ds, i) {
      var colour = palette[i % palette.length];
      return Object.assign({}, ds, { backgroundColor: colour, borderColor: colour, borderWidth: 2,
                                     tension: 0.25, fill: false, maxBarThickness: 40 });
    });
    new Chart(canvas, {
      type: type === "line" ? "line" : "bar",
      data: { labels: data.labels, datasets: datasets },
      options: {
        responsive: true, maintainAspectRatio: false,
        scales: {
          x: { stacked: type === "stacked", ticks: { maxRotation: 60 } },
          y: { stacked: type === "stacked", beginAtZero: true, ticks: { precision: 0 } }
        },
        plugins: { legend: { display: datasets.length > 1 } }
      }
    });
  });
})();
