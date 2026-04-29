document.addEventListener("DOMContentLoaded", function () {
  const metricSelect = document.getElementById("mapMetricSelect");
  const filterSelect = document.getElementById("mapFilterSelect");
  const pairSelect = document.getElementById("mapPairSelect");
  const mapFrame = document.getElementById("mapFrame");


  function bindPlotClick() {
    const plot = document.querySelector("#mapFrame .js-plotly-plot");

   

    if (!plot) return;

    plot.on("plotly_click", function (data) {

      const point = data.points && data.points[0];
      if (!point) return;

      let sourceEntity = null;
      if (point.customdata && point.customdata.length > 0) {
        sourceEntity = point.customdata[0];
      }


      if (!sourceEntity) return;

      if (typeof window.setActiveSummaryEntity === "function") {
        window.setActiveSummaryEntity(sourceEntity, {
          syncDropdown: false,
          scrollToRow: true,
        });
      }

      if (typeof window.loadEntityByName === "function") {
        window.loadEntityByName(sourceEntity);
      } else {
        return;
      }

      window.addEventListener(
        "entity:loaded",
        () => {
          document.getElementById("entityChartWrap")?.scrollIntoView({
            behavior: "smooth",
            block: "start",
          });
        },
        { once: true }
      );
    });
  }

  function getSelectedPair() {
    if (!pairSelect || !pairSelect.value) {
      return { x: "", y: "" };
    }

    const value = pairSelect.value;
    const separator = "|||";

    if (!value.includes(separator)) {
      return { x: "", y: "" };
    }

    const [x, y] = value.split(separator);
    return {
      x: x || "",
      y: y || "",
    };
  }

  async function loadAvailablePairs() {
    if (!pairSelect) return;

    try {
      const response = await fetch("/api/available-pairs/", {
        headers: {
          "X-Requested-With": "XMLHttpRequest",
        },
      });

      if (!response.ok) {
        pairSelect.innerHTML = "<option value=''>No pairs available</option>";
        return;
      }

      const data = await response.json();
      const pairs = Array.isArray(data.pairs) ? data.pairs : [];

      pairSelect.innerHTML = "";

      const defaultOption = document.createElement("option");
      defaultOption.value = "";
      defaultOption.textContent = "Top pair per country";
      pairSelect.appendChild(defaultOption);

      pairs.forEach((pair) => {
        const option = document.createElement("option");
        option.value = `${pair.x}|||${pair.y}`;
        option.textContent = pair.label || `${pair.x} vs ${pair.y}`;
        pairSelect.appendChild(option);
      });
    } catch (err) {
      console.error("Failed to load available pairs", err);
      pairSelect.innerHTML = "<option value=''>No pairs available</option>";
    }
  }

  async function refreshMap() {
    if (!mapFrame || !metricSelect || !filterSelect) return;

    const metric = metricSelect.value;
    const significantOnly = filterSelect.value === "significant" ? "1" : "0";
    const { x, y } = getSelectedPair();

    const params = new URLSearchParams({
      metric: metric,
      significant_only: significantOnly,
    });

    if (x && y) {
      params.append("x", x);
      params.append("y", y);
    }

    const url = `/api/map-fragment/?${params.toString()}`;

    try {
      const response = await fetch(url, {
        headers: {
          "X-Requested-With": "XMLHttpRequest",
        },
      });

      if (!response.ok) {
        mapFrame.innerHTML = "<div class='muted'>Failed to load map.</div>";
        return;
      }

      const html = await response.text();
      mapFrame.innerHTML = html;

      const scripts = mapFrame.querySelectorAll("script");
      scripts.forEach((oldScript) => {
        const newScript = document.createElement("script");

        for (const attr of oldScript.attributes) {
          newScript.setAttribute(attr.name, attr.value);
        }

        newScript.textContent = oldScript.textContent;
        oldScript.parentNode.replaceChild(newScript, oldScript);
      });

      setTimeout(() => {
        bindPlotClick();
      }, 200);
    } catch (err) {
      console.error(err);
      mapFrame.innerHTML = "<div class='muted'>Failed to load map.</div>";
    }
  }

  if (metricSelect) {
    metricSelect.addEventListener("change", refreshMap);
  }

  if (filterSelect) {
    filterSelect.addEventListener("change", refreshMap);
  }

  if (pairSelect) {
    pairSelect.addEventListener("change", refreshMap);
  }

  window.addEventListener("analysis:updated", async () => {
    await loadAvailablePairs();
    await refreshMap();
  });

  (async function initMap() {
    await loadAvailablePairs();
    await refreshMap();
  })();

  window.refreshAnalysisMap = refreshMap;
});