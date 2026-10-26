(function () {
  const roundSwitch = document.getElementById("round-switch");
  if (roundSwitch) {
    roundSwitch.addEventListener("change", function () {
      if (roundSwitch.value) window.location.assign(roundSwitch.value);
    });
  }

  const chartNode = document.getElementById("chart-data");
  const chartHost = document.getElementById("lap-chart");
  if (chartNode && chartHost) drawChart(JSON.parse(chartNode.textContent), chartHost);

  const traceNode = document.getElementById("trace-data");
  const traceCanvas = document.getElementById("trace-canvas");
  if (traceNode && traceCanvas) drawTraces(JSON.parse(traceNode.textContent), traceCanvas);

  const replay = document.getElementById("replay");
  if (replay) bindReplay(replay);
})();

function drawChart(data, host) {
  const laps = data.laps || [];
  const series = data.series || [];
  if (!laps.length || !series.length) return;
  let places = 1;
  series.forEach(function (row) {
    (row.positions || []).forEach(function (value) {
      if (typeof value === "number" && value > places) places = value;
    });
  });
  const width = Math.max(720, laps.length * 11 + 56);
  const height = Math.max(240, places * 14 + 36);
  const left = 36;
  const top = 16;
  const plotW = width - left - 12;
  const plotH = height - top - 20;
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("viewBox", "0 0 " + width + " " + height);
  svg.setAttribute("width", String(width));
  svg.setAttribute("height", String(height));
  svg.setAttribute("role", "img");
  svg.setAttribute("aria-label", "Position of each driver at the start of each lap");

  for (let place = 1; place <= places; place += Math.max(1, Math.round(places / 8))) {
    const y = top + ((place - 1) / Math.max(places - 1, 1)) * plotH;
    const label = document.createElementNS("http://www.w3.org/2000/svg", "text");
    label.setAttribute("x", "4");
    label.setAttribute("y", String(y + 4));
    label.setAttribute("fill", "#5e584e");
    label.setAttribute("font-size", "11");
    label.textContent = String(place);
    svg.appendChild(label);
  }

  series.forEach(function (row) {
    const colour = "#" + (row.colour || "888888");
    let drawing = false;
    let path = "";
    (row.positions || []).forEach(function (value, index) {
      if (typeof value !== "number") {
        drawing = false;
        return;
      }
      const x = left + (laps.length === 1 ? plotW / 2 : (index / (laps.length - 1)) * plotW);
      const y = top + ((value - 1) / Math.max(places - 1, 1)) * plotH;
      path += (drawing ? " L" : " M") + x.toFixed(1) + " " + y.toFixed(1);
      drawing = true;
    });
    if (!path) return;
    const line = document.createElementNS("http://www.w3.org/2000/svg", "path");
    line.setAttribute("d", path.trim());
    line.setAttribute("fill", "none");
    line.setAttribute("stroke", colour);
    line.setAttribute("stroke-width", "1.6");
    svg.appendChild(line);
  });
  host.appendChild(svg);
}

function drawTraces(data, canvas) {
  const traces = data.traces || [];
  const brakes = data.brakes || [];
  const ctx = canvas.getContext("2d");
  const width = canvas.width;
  const height = canvas.height;
  ctx.clearRect(0, 0, width, height);
  let minS = Infinity;
  let maxS = -Infinity;
  let minV = Infinity;
  let maxV = -Infinity;
  traces.forEach(function (trace) {
    (trace.s || []).forEach(function (s, index) {
      const speed = trace.speed[index];
      if (typeof s !== "number" || typeof speed !== "number") return;
      minS = Math.min(minS, s);
      maxS = Math.max(maxS, s);
      minV = Math.min(minV, speed);
      maxV = Math.max(maxV, speed);
    });
  });
  if (!isFinite(minS) || maxS === minS) return;
  const pad = 28;
  const spanV = Math.max(maxV - minV, 1);
  function xOf(s) {
    return pad + ((s - minS) / (maxS - minS)) * (width - pad * 2);
  }
  function yOf(speed) {
    return height - pad - ((speed - minV) / spanV) * (height - pad * 2);
  }
  ctx.strokeStyle = "#d9d1c3";
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.moveTo(pad, pad);
  ctx.lineTo(pad, height - pad);
  ctx.lineTo(width - pad, height - pad);
  ctx.stroke();
  ctx.fillStyle = "#5e584e";
  ctx.font = "12px ui-monospace, Menlo, Consolas, monospace";
  ctx.fillText(Math.round(maxV) + " km/h", 4, pad + 4);
  ctx.fillText(Math.round(minS) + " m", pad, height - 8);
  ctx.fillText(Math.round(maxS) + " m", width - pad - 48, height - 8);

  traces.forEach(function (trace) {
    ctx.beginPath();
    ctx.strokeStyle = "#" + (trace.colour || "888888");
    ctx.lineWidth = 2;
    let started = false;
    (trace.s || []).forEach(function (s, index) {
      const speed = trace.speed[index];
      if (typeof s !== "number" || typeof speed !== "number") {
        started = false;
        return;
      }
      const x = xOf(s);
      const y = yOf(speed);
      if (!started) {
        ctx.moveTo(x, y);
        started = true;
      } else ctx.lineTo(x, y);
    });
    ctx.stroke();
  });

  brakes.forEach(function (driver) {
    if (typeof driver.brake_m !== "number") return;
    const x = xOf(driver.brake_m);
    ctx.strokeStyle = "#" + (driver.colour || "888888");
    ctx.setLineDash([3, 3]);
    ctx.beginPath();
    ctx.moveTo(x, pad);
    ctx.lineTo(x, height - pad);
    ctx.stroke();
    ctx.setLineDash([]);
  });
}

function bindReplay(panel) {
  const load = document.getElementById("replay-load");
  const play = document.getElementById("replay-play");
  const rate = document.getElementById("replay-rate");
  const scrub = document.getElementById("replay-scrub");
  const clock = document.getElementById("replay-clock");
  const status = document.getElementById("replay-status");
  const canvas = document.getElementById("replay-canvas");
  const session = panel.dataset.session;
  let documentData = null;
  let t = 0;
  let playing = false;
  let last = 0;

  function setClock() {
    clock.textContent = formatRaceTime(t);
    if (documentData) scrub.value = String(Math.round(t * 10));
  }

  function frame(now) {
    if (!playing || !documentData) return;
    if (!last) last = now;
    const scale = Number(rate.value) || 1;
    t = Math.min(documentData.duration_s, t + ((now - last) / 1000) * scale);
    last = now;
    if (t >= documentData.duration_s) {
      playing = false;
      play.textContent = "Play";
    }
    setClock();
    paintReplay(canvas, documentData, t);
    if (playing) requestAnimationFrame(frame);
  }

  load.addEventListener("click", function () {
    status.textContent = "Loading the location stream. The first time for a race reads every car.";
    load.disabled = true;
    fetch("/api/race/" + session + "/replay")
      .then(function (response) {
        if (!response.ok) throw new Error("Replay unavailable");
        return response.json();
      })
      .then(function (payload) {
        documentData = payload;
        t = 0;
        scrub.max = String(Math.max(0, Math.round(payload.duration_s * 10)));
        scrub.disabled = false;
        play.disabled = !payload.cars.length;
        status.textContent = payload.cars.length
          ? payload.cars.length + " cars, one sample every " + payload.step_s + " s. The line is the timing map."
          : "No location samples for this session.";
        setClock();
        paintReplay(canvas, documentData, t);
      })
      .catch(function () {
        status.textContent = "The location stream could not be loaded.";
        load.disabled = false;
      });
  });

  play.addEventListener("click", function () {
    if (!documentData) return;
    playing = !playing;
    play.textContent = playing ? "Pause" : "Play";
    last = 0;
    if (playing) requestAnimationFrame(frame);
  });

  scrub.addEventListener("input", function () {
    t = Number(scrub.value) / 10;
    setClock();
    if (documentData) paintReplay(canvas, documentData, t);
  });

  panel.addEventListener("keydown", function (event) {
    if (!documentData) return;
    if (event.key === " " || event.code === "Space") {
      event.preventDefault();
      play.click();
    } else if (event.key === "ArrowRight") {
      t = Math.min(documentData.duration_s, t + 2);
      setClock();
      paintReplay(canvas, documentData, t);
    } else if (event.key === "ArrowLeft") {
      t = Math.max(0, t - 2);
      setClock();
      paintReplay(canvas, documentData, t);
    }
  });
}

function paintReplay(canvas, data, t) {
  const ctx = canvas.getContext("2d");
  const width = canvas.width;
  const height = canvas.height;
  ctx.fillStyle = "#221f1a";
  ctx.fillRect(0, 0, width, height);
  const points = (data.track || []).slice();
  (data.cars || []).forEach(function (car) {
    const sample = sampleAt(car.samples, t);
    if (sample) points.push([sample.x, sample.y]);
  });
  if (!points.length) return;
  let minX = Infinity;
  let maxX = -Infinity;
  let minY = Infinity;
  let maxY = -Infinity;
  points.forEach(function (point) {
    minX = Math.min(minX, point[0]);
    maxX = Math.max(maxX, point[0]);
    minY = Math.min(minY, point[1]);
    maxY = Math.max(maxY, point[1]);
  });
  const pad = 24;
  const spanX = Math.max(maxX - minX, 1);
  const spanY = Math.max(maxY - minY, 1);
  const scale = Math.min((width - pad * 2) / spanX, (height - pad * 2) / spanY);
  function px(x, y) {
    const sx = pad + (x - minX) * scale;
    const sy = height - pad - (y - minY) * scale;
    return [sx, sy];
  }
  ctx.strokeStyle = "#6d675c";
  ctx.lineWidth = 2;
  ctx.beginPath();
  (data.track || []).forEach(function (point, index) {
    const mapped = px(point[0], point[1]);
    if (index === 0) ctx.moveTo(mapped[0], mapped[1]);
    else ctx.lineTo(mapped[0], mapped[1]);
  });
  ctx.stroke();
  (data.cars || []).forEach(function (car) {
    const sample = sampleAt(car.samples, t);
    if (!sample) return;
    const mapped = px(sample.x, sample.y);
    ctx.fillStyle = "#" + (car.colour || "f4f1ea");
    ctx.beginPath();
    ctx.arc(mapped[0], mapped[1], 5, 0, Math.PI * 2);
    ctx.fill();
    ctx.fillStyle = "#f4f1ea";
    ctx.font = "11px ui-monospace, Menlo, Consolas, monospace";
    ctx.fillText(car.code, mapped[0] + 7, mapped[1] - 7);
  });
}

function sampleAt(samples, t) {
  if (!samples || !samples.length) return null;
  if (t <= samples[0].t) return samples[0];
  const last = samples[samples.length - 1];
  if (t >= last.t) return last;
  let low = 0;
  let high = samples.length - 1;
  while (low + 1 < high) {
    const mid = (low + high) >> 1;
    if (samples[mid].t <= t) low = mid;
    else high = mid;
  }
  const left = samples[low];
  const right = samples[high];
  const span = right.t - left.t || 1;
  const mix = (t - left.t) / span;
  return {
    x: left.x + (right.x - left.x) * mix,
    y: left.y + (right.y - left.y) * mix,
  };
}

function formatRaceTime(seconds) {
  const whole = Math.max(0, Math.floor(seconds));
  const hours = Math.floor(whole / 3600);
  const minutes = Math.floor((whole % 3600) / 60);
  const secs = whole % 60;
  const pad = function (value) { return String(value).padStart(2, "0"); };
  if (hours) return hours + ":" + pad(minutes) + ":" + pad(secs);
  return pad(minutes) + ":" + pad(secs);
}
