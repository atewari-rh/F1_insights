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
  let focusCodes = null;

  function setClock() {
    clock.textContent = raceClock(documentData, t);
    if (!documentData) return;
    scrub.value = String(Math.round(t * 10));
    paintReplay(canvas, documentData, t, focusCodes, rate.value);
  }

  function frame(now) {
    if (!playing || !documentData) return;
    if (!last) last = now;
    const step = Math.min(0.25, (now - last) / 1000);
    last = now;
    const scale = Number(rate.value) || 1;
    t = Math.min(documentData.duration_s, t + step * scale);
    if (t >= documentData.duration_s) {
      playing = false;
      play.textContent = "Play";
    }
    try {
      setClock();
    } catch (error) {
      clock.textContent = raceClock(documentData, t);
    }
    if (playing) requestAnimationFrame(frame);
  }

  load.addEventListener("click", function () {
    load.disabled = true;
    load.textContent = "Loading…";
    panel.scrollIntoView({ block: "nearest" });
    const started = Date.now();
    paintReplayMessage(canvas, "Loading the circuit…");
    status.textContent = "Reading every car. The first time for a race can take a couple of minutes.";
    const timer = setInterval(function () {
      const seconds = Math.round((Date.now() - started) / 1000);
      status.textContent = "Reading every car (" + seconds + " s). The first time for a race can take a couple of minutes.";
      paintReplayMessage(canvas, "Loading the circuit… " + seconds + "s");
    }, 1000);
    fetch("/api/race/" + session + "/replay")
      .then(function (response) {
        if (!response.ok) throw new Error("Replay unavailable");
        return response.json();
      })
      .then(function (payload) {
        clearInterval(timer);
        documentData = payload;
        prepareTrack(documentData);
        focusCodes = null;
        const green = Number(payload.race_start_s) || 0;
        t = Math.min(payload.duration_s, Math.max(0, green));
        scrub.max = String(Math.max(0, Math.round(payload.duration_s * 10)));
        scrub.disabled = false;
        play.disabled = !payload.cars.length;
        load.textContent = "Loaded";
        status.textContent = payload.cars.length
          ? payload.cars.length + " cars, one sample every " + payload.step_s + " s."
          : "No location samples for this session.";
        setClock();
      })
      .catch(function () {
        clearInterval(timer);
        status.textContent = "The location stream could not be loaded.";
        load.disabled = false;
        load.textContent = "Load replay";
        paintReplayMessage(canvas, "The location stream could not be loaded.");
      });
  });

  play.addEventListener("click", function () {
    if (!documentData) return;
    playing = !playing;
    play.textContent = playing ? "Pause" : "Play";
    last = 0;
    if (playing && documentData.race_start_s && t < documentData.race_start_s - 15) {
      t = documentData.race_start_s;
    }
    if (playing) requestAnimationFrame(frame);
  });

  scrub.addEventListener("input", function () {
    t = Number(scrub.value) / 10;
    setClock();
  });

  const order = document.getElementById("replay-order");
  if (order) {
    order.addEventListener("click", function (event) {
      const row = event.target.closest("li");
      if (!row || !documentData) return;
      const code = row.dataset.code;
      if (!code) return;
      const current = focusCodes
        ? focusCodes.slice()
        : standings(documentData, t).slice(0, 3).map(function (item) { return item.car.code; });
      const index = current.indexOf(code);
      if (index >= 0) current.splice(index, 1);
      else current.unshift(code);
      focusCodes = current.slice(0, 3);
      setClock();
    });
  }

  canvas.addEventListener("click", function (event) {
    if (!documentData || !boardHits.length) return;
    const rect = canvas.getBoundingClientRect();
    const x = (event.clientX - rect.left) / rect.width * 1024;
    const y = (event.clientY - rect.top) / rect.height * 578;
    const hit = boardHits.find(function (row) {
      return x >= row.x && x <= row.x + row.w && y >= row.y && y <= row.y + row.h;
    });
    if (!hit) return;
    const current = focusCodes
      ? focusCodes.slice()
      : standings(documentData, t).slice(0, 3).map(function (item) { return item.car.code; });
    const index = current.indexOf(hit.code);
    if (index >= 0) current.splice(index, 1);
    current.unshift(hit.code);
    focusCodes = current.slice(0, 3);
    setClock();
  });

  window.addEventListener("keydown", function (event) {
    if (!documentData) return;
    const typing = event.target && /^(INPUT|SELECT|TEXTAREA)$/.test(event.target.tagName);
    if (typing) return;
    if (event.key === " " || event.code === "Space") {
      event.preventDefault();
      play.click();
    } else if (event.key === "ArrowRight") {
      event.preventDefault();
      t = Math.min(documentData.duration_s, t + 2);
      setClock();
    } else if (event.key === "ArrowLeft") {
      event.preventDefault();
      t = Math.max(0, t - 2);
      setClock();
    } else if (event.key === "ArrowUp" || event.key === "ArrowDown") {
      event.preventDefault();
      const options = Array.from(rate.options).map(function (option) { return option.value; });
      const index = options.indexOf(rate.value);
      const next = event.key === "ArrowUp" ? Math.min(options.length - 1, index + 1) : Math.max(0, index - 1);
      rate.value = options[next];
      setClock();
    }
  });
}

function paintReplayMessage(canvas, text) {
  const ctx = canvas.getContext("2d");
  ctx.fillStyle = "#221f1a";
  ctx.fillRect(0, 0, canvas.width, canvas.height);
  ctx.fillStyle = "#f4f1ea";
  ctx.font = "18px ui-monospace, Menlo, Consolas, monospace";
  ctx.fillText(text, 28, 48);
}

function paintReplay(canvas, data, t) {
  const ctx = canvas.getContext("2d");
  const width = canvas.width;
  const height = canvas.height;
  ctx.fillStyle = "#221f1a";
  ctx.fillRect(0, 0, width, height);
  const track = data.track || [];
  const points = track.slice();
  if (points.length < 2) {
    (data.cars || []).forEach(function (car) {
      const sample = sampleAt(car.samples, t);
      if (sample) points.push([sample.x, sample.y]);
    });
  }
  if (!points.length) return;
=======
function paintReplayMessage(canvas, text) {
  const ctx = canvas.getContext("2d");
  if (canvas.width !== REF_W * 2 || canvas.height !== REF_H * 2) {
    canvas.width = REF_W * 2;
    canvas.height = REF_H * 2;
  }
  ctx.setTransform(2, 0, 0, 2, 0, 0);
  ctx.fillStyle = "#000";
  ctx.fillRect(0, 0, REF_W, REF_H);
  ctx.fillStyle = "#f4f4f4";
  ctx.font = "16px Arial, Helvetica, sans-serif";
  ctx.textBaseline = "top";
  ctx.fillText(text, 12, 24);
}

function renderSide(data, t, speed, focusCodes) {
  const lap = document.getElementById("replay-lap");
  const race = document.getElementById("replay-race");
  const weather = document.getElementById("replay-weather");
  const order = document.getElementById("replay-order");
  const cards = document.getElementById("replay-cards");
  if (!lap || !race || !weather || !order) return;
  if (!data) {
    lap.textContent = "Lap: —";
    race.textContent = "Race Time: —";
    return;
  }
  const rows = standings(data, t);
  const leader = rows.length ? rows[0].car : null;
  const lapNumber = leader ? valueAt(leader.laps, t, "n") : null;
  const total = data.lap_total;
  if (lapNumber) lap.textContent = "Lap: " + lapNumber + (total ? "/" + total : "");
  else lap.textContent = "Lap: —";
  const rate = Number(speed);
  race.textContent = "Race Time: " + formatHudTime(raceSeconds(data, t)) + " (x" + (Number.isFinite(rate) ? rate.toFixed(1) : "1.0") + ")";
  paintWeather(weather, latestAt(data.weather, t) || (data.weather || [])[0] || null);
  paintBoard(order, rows, focusCodes);
  if (cards) paintCards(cards, data, rows, focusCodes);
}

function leaderAt(data, t) {
  const rows = standings(data, t);
  return rows.length ? rows[0].car : null;
}

function standings(data, t) {
  return (data.cars || []).map(function (car) {
    const sample = sampleAt(car.samples, t);
    return {
      car: car,
      place: valueAt(car.places, t, "p"),
      lap: valueAt(car.laps, t, "n"),
      sample: sample,
      arc: sample && data._arc ? arcOf(data, sample.x, sample.y) : 0,
      live: sample ? sample.live : false,
    };
  }).filter(function (row) {
    return typeof row.place === "number";
  }).sort(function (left, right) {
    return left.place - right.place || left.car.code.localeCompare(right.car.code);
  });
}

function paintWeather(host, sample) {
  const key = sample
    ? [sample.t, sample.track, sample.air, sample.humidity, sample.wind, sample.wind_from, sample.rain].join("|")
    : "";
  if (host.dataset.t === key) return;
  host.dataset.t = key;
  host.replaceChildren();
  if (!sample) return;
  const lines = [
    ["track", sample.track == null ? "" : "Track: " + sample.track + "°C"],
    ["air", sample.air == null ? "" : "Air: " + sample.air + "°C"],
    ["humidity", sample.humidity == null ? "" : "Humidity: " + Math.round(sample.humidity) + "%"],
    ["wind", sample.wind == null ? "" : "Wind: " + sample.wind + " m/s" + (sample.wind_from ? " " + sample.wind_from : "")],
    ["rain", sample.rain == null ? "" : (sample.rain > 0 ? "Rain: " + sample.rain : "Rain: DRY")],
  ];
  lines.forEach(function (line) {
    if (!line[1]) return;
    const row = document.createElement("p");
    row.className = "wx";
    row.append(weatherIcon(line[0]), document.createTextNode(line[1]));
    host.appendChild(row);
  });
}

function paintBoard(order, rows, focusCodes) {
  const focus = focusCodes && focusCodes.length ? focusCodes : rows.slice(0, 3).map(function (row) { return row.car.code; });
  const signature = rows.map(function (row) {
    return row.place + row.car.code + (row.live ? "" : "out");
  }).join(",") + "|" + focus.join(",");
  if (order.dataset.signature === signature) return;
  order.dataset.signature = signature;
  order.replaceChildren();
  rows.forEach(function (row) {
    const item = document.createElement("li");
    item.dataset.code = row.car.code;
    if (focus.indexOf(row.car.code) >= 0) item.className = "focused";
    const place = document.createElement("span");
    place.className = "replay-pos";
    place.textContent = String(row.place);
    const code = document.createElement("span");
    code.textContent = row.car.code;
    code.style.color = cssColour(row.car.colour);
    item.append(place, code);
    if (row.live) {
      const dot = document.createElement("span");
      dot.className = "replay-dot";
      item.appendChild(dot);
    } else {
      const out = document.createElement("span");
      out.className = "replay-out";
      out.textContent = "OUT";
      item.appendChild(out);
    }
    order.appendChild(item);
  });
}

function paintCards(host, data, rows, focusCodes) {
  const focus = focusCodes && focusCodes.length ? focusCodes : rows.slice(0, 3).map(function (row) { return row.car.code; });
  const chosen = focus.map(function (code) {
    return rows.find(function (row) { return row.car.code === code; });
  }).filter(Boolean).slice(0, 3);
  if (host.dataset.key !== focus.join(",")) {
    host.dataset.key = focus.join(",");
    host.replaceChildren();
    chosen.forEach(function () {
      host.appendChild(cardShell());
    });
  }
  while (host.children.length < chosen.length) host.appendChild(cardShell());
  while (host.children.length > chosen.length) host.removeChild(host.lastChild);
  chosen.forEach(function (row, index) {
    const ahead = rows.find(function (item) { return item.place === row.place - 1; });
    const behind = rows.find(function (item) { return item.place === row.place + 1; });
    fillCard(host.children[index], data, row, ahead, behind);
  });
}

function cardShell() {
  const card = document.createElement("article");
  card.className = "driver-card";
  card.innerHTML = '<h3></h3><div class="driver-body"><div class="driver-copy"><p class="line-speed"></p><p class="line-gear"></p><p class="line-drs"></p><p class="line-ahead"></p><p class="line-behind"></p></div><div class="pedals"><div class="pedal-col"><div class="pedal pedal-throttle"><i></i></div><span>THR</span></div><div class="pedal-col"><div class="pedal pedal-brake"><i></i></div><span>BRK</span></div></div></div>';
  return card;
}

function fillCard(card, data, row, ahead, behind) {
  const colour = cssColour(row.car.colour);
  card.style.borderColor = colour;
  const title = card.querySelector("h3");
  title.textContent = "Driver: " + row.car.code;
  title.style.background = colour;
  const sample = row.sample;
  card.querySelector(".line-speed").textContent = "Speed: " + (sample && sample.speed != null ? sample.speed + " km/h" : "N/A");
  card.querySelector(".line-gear").textContent = "Gear: " + (sample && sample.gear != null ? sample.gear : "N/A");
  card.querySelector(".line-drs").textContent = "DRS: " + (sample && sample.drs == null ? "N/A" : sample && sample.drs ? "ON" : "OFF");
  card.querySelector(".line-ahead").textContent = ahead ? "Ahead " + gapLabel(data, row, ahead, 1) : "Ahead: N/A";
  card.querySelector(".line-behind").textContent = behind ? "Behind " + gapLabel(data, row, behind, -1) : "Behind: N/A";
  const throttle = sample && sample.throttle != null ? sample.throttle : 0;
  const brake = sample && sample.brake != null ? sample.brake : 0;
  card.querySelector(".pedal-throttle i").style.height = throttle + "%";
  card.querySelector(".pedal-brake i").style.height = brake + "%";
}

function gapLabel(data, row, other, sign) {
  const mine = typeof row.lap === "number" ? row.lap : null;
  const theirs = typeof other.lap === "number" ? other.lap : null;
  if (mine != null && theirs != null && Math.abs(theirs - mine) >= 1) {
    const laps = Math.abs(theirs - mine);
    return "(" + other.car.code + "): +" + laps + (laps === 1 ? " LAP" : " LAPS");
  }
  const length = data._lap || 1;
  let meters = other.arc - row.arc;
  meters = ((meters % length) + length) % length;
  if (meters > length / 2) meters = length - meters;
  const speed = row.sample && row.sample.speed > 40 ? row.sample.speed : 200;
  const seconds = meters / (speed / 3.6);
  const mark = sign < 0 ? "-" : "+";
  return "(" + other.car.code + "): " + mark + seconds.toFixed(2) + "s (" + meters.toFixed(1) + "m)";
}

function prepareTrack(data) {
  const track = data.track || [];
  const arc = [0];
  for (let index = 1; index < track.length; index += 1) {
    arc.push(arc[index - 1] + Math.hypot(track[index][0] - track[index - 1][0], track[index][1] - track[index - 1][1]));
  }
  data._arc = arc;
  data._lap = arc.length ? arc[arc.length - 1] : 1;
}

function arcOf(data, x, y) {
  const track = data.track || [];
  let best = 0;
  let bestDistance = Infinity;
  for (let index = 0; index < track.length; index += 2) {
    const distance = (track[index][0] - x) * (track[index][0] - x) + (track[index][1] - y) * (track[index][1] - y);
    if (distance < bestDistance) {
      bestDistance = distance;
      best = index;
    }
  }
  return data._arc[best] || 0;
}

function weatherIcon(kind) {
  const paths = {
    track: '<path d="M8 1.5v8.2M5.2 3.2h5.6M6.2 14.2a2.2 2.2 0 1 1 3.6 0" />',
    air: '<path d="M3 8h8.2a2 2 0 1 0-1.6-3.2M2.5 11h7.2a1.7 1.7 0 1 1-1.3 2.8" />',
    humidity: '<path d="M8 2.2s4 4.2 4 7a4 4 0 0 1-8 0c0-2.8 4-7 4-7z" />',
    wind: '<path d="M2 6h8.5a1.8 1.8 0 1 0-1.4-2.9M2 9.5h10a1.8 1.8 0 1 1-1.4 2.9" />',
    rain: '<path d="M4 7.2A3.2 3.2 0 0 1 8.8 4 3 3 0 0 1 13 7.4M5 11l-.8 2M8 11l-.8 2M11 11l-.8 2" />',
  };
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("viewBox", "0 0 16 16");
  svg.setAttribute("width", "13");
  svg.setAttribute("height", "13");
  svg.setAttribute("fill", "none");
  svg.setAttribute("stroke", "#d7d7d7");
  svg.setAttribute("stroke-width", "1.3");
  svg.innerHTML = paths[kind] || "";
  return svg;
}

function formatHudTime(seconds) {
  const whole = Math.max(0, Math.floor(seconds));
  const hours = Math.floor(whole / 3600);
  const minutes = Math.floor((whole % 3600) / 60);
  const secs = whole % 60;
  const pad = function (value) { return String(value).padStart(2, "0"); };
  return pad(hours) + ":" + pad(minutes) + ":" + pad(secs);
}

function raceSeconds(data, t) {
  const start = data && typeof data.race_start_s === "number" ? data.race_start_s : 0;
  return Math.max(0, t - start);
}

function raceClock(data, t) {
  return formatHudTime(raceSeconds(data, t));
}

function cssColour(value) {
  return /^[0-9a-fA-F]{6}$/.test(value || "") ? "#" + value : "#f4f1ea";
}

function latestAt(samples, t) {
  if (!samples || !samples.length || t < samples[0].t) return null;
  let low = 0;
  let high = samples.length - 1;
  while (low + 1 < high) {
    const mid = (low + high) >> 1;
    if (samples[mid].t <= t) low = mid;
    else high = mid;
  }
  return samples[samples[high].t <= t ? high : low];
}

function valueAt(samples, t, key) {
  const sample = latestAt(samples, t);
  return sample ? sample[key] : null;
}

const REF_W = 1024;
const REF_H = 578;
let boardHits = [];

function paintReplay(canvas, data, t, focusCodes, speed) {
  const ctx = canvas.getContext("2d");
  if (canvas.width !== REF_W * 2 || canvas.height !== REF_H * 2) {
    canvas.width = REF_W * 2;
    canvas.height = REF_H * 2;
  }
  ctx.setTransform(2, 0, 0, 2, 0, 0);
  ctx.fillStyle = "#000";
  ctx.fillRect(0, 0, REF_W, REF_H);
  ctx.lineJoin = "round";
  ctx.lineCap = "round";
  ctx.font = "12px Arial, Helvetica, sans-serif";
  const track = data.track || [];
  const fit = fitTrack(track.length > 1 ? track : []);
  if (fit && track.length > 1) {
    strokePath(ctx, track, null, fit.px);
    ctx.strokeStyle = "#d7d7d7";
    ctx.lineWidth = 2.15;
    ctx.stroke();
    if ((data.drs || []).some(function (flag) { return flag; })) {
      strokePath(ctx, track, data.drs, fit.px);
      ctx.strokeStyle = "#00ff00";
      ctx.lineWidth = 2.7;
      ctx.stroke();
    }
  }
  (data.cars || []).forEach(function (car) {
    const sample = sampleAt(car.samples, t);
    if (!sample || sample.live === false || !fit) return;
    const mapped = fit.px(sample.x, sample.y);
    ctx.beginPath();
    ctx.arc(mapped[0], mapped[1], 3.3, 0, Math.PI * 2);
    ctx.fillStyle = cssColour(car.colour);
    ctx.fill();
  });
  paintHud(ctx, data, t, focusCodes, speed);
}

function fitTrack(track) {
  if (!track.length) return null;
  let minX = Infinity;
  let maxX = -Infinity;
  let minY = Infinity;
  let maxY = -Infinity;
  track.forEach(function (point) {
    minX = Math.min(minX, point[0]);
    maxX = Math.max(maxX, point[0]);
    minY = Math.min(minY, point[1]);
    maxY = Math.max(maxY, point[1]);
  });
  if (track.length > 1) {
    minX -= 80;
    maxX += 80;
    minY -= 80;
    maxY += 80;
  }
  const pad = 36;
  const spanX = Math.max(maxX - minX, 1);
  const spanY = Math.max(maxY - minY, 1);
  const scale = Math.min((width - pad * 2) / spanX, (height - pad * 2) / spanY);
  const usedX = spanX * scale;
  const usedY = spanY * scale;
  const offsetX = (width - usedX) / 2;
  const offsetY = (height - usedY) / 2;
  function px(x, y) {
    const sx = offsetX + (x - minX) * scale;
    const sy = offsetY + usedY - (y - minY) * scale;
    return [sx, sy];
  }
  if (track.length > 1) {
    const metres = data.track_width_m || 14;
    const ribbon = Math.max(18, metres * scale);
    ctx.lineJoin = "round";
    ctx.lineCap = "round";
    ctx.beginPath();
    track.forEach(function (point, index) {
      const mapped = px(point[0], point[1]);
      if (index === 0) ctx.moveTo(mapped[0], mapped[1]);
      else ctx.lineTo(mapped[0], mapped[1]);
    });
    ctx.strokeStyle = "#0e0d0b";
    ctx.lineWidth = ribbon + 8;
    ctx.stroke();
    ctx.strokeStyle = "#8a8376";
    ctx.lineWidth = ribbon;
    ctx.stroke();
    ctx.strokeStyle = "#d9d0c2";
    ctx.lineWidth = Math.max(2, ribbon * 0.12);
    ctx.stroke();
  }
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
=======
  const spanX = Math.max(maxX - minX, 1);
  const spanY = Math.max(maxY - minY, 1);
  const pad = Math.max(spanX, spanY) * 0.04;
  minX -= pad;
  maxX += pad;
  minY -= pad;
  maxY += pad;
  const boxX = 176;
  const boxY = 10;
  const boxW = 700;
  const boxH = 556;
  const scale = Math.min(boxW / (maxX - minX), boxH / (maxY - minY));
  const usedX = (maxX - minX) * scale;
  const usedY = (maxY - minY) * scale;
  const offsetX = boxX + (boxW - usedX) / 2;
  const offsetY = boxY + (boxH - usedY) / 2;
  return {
    px: function (x, y) {
      return [offsetX + (x - minX) * scale, offsetY + usedY - (y - minY) * scale];
    },
  };
}

function paintHud(ctx, data, t, focusCodes, speed) {
  const rows = standings(data, t);
  const leader = rows.length ? rows[0].car : null;
  const lapNumber = leader ? valueAt(leader.laps, t, "n") : null;
  const total = data.lap_total;
  ctx.fillStyle = "#f4f4f4";
  ctx.font = "bold 15px Arial, Helvetica, sans-serif";
  ctx.textBaseline = "top";
  ctx.fillText(lapNumber ? "Lap: " + lapNumber + (total ? "/" + total : "") : "Lap: —", 10, 22);
  const rate = Number(speed);
  ctx.font = "bold 13px Arial, Helvetica, sans-serif";
  ctx.fillText(
    "Race Time: " + formatHudTime(raceSeconds(data, t)) + " (x" + (Number.isFinite(rate) ? rate.toFixed(1) : "1.0") + ")",
    10,
    42
  );
  ctx.font = "bold 13px Arial, Helvetica, sans-serif";
  ctx.fillText("Weather", 10, 96);
  const weather = latestAt(data.weather, t) || (data.weather || [])[0] || null;
  const lines = weather ? [
    ["track", weather.track == null ? "" : "Track: " + weather.track + "°C"],
    ["air", weather.air == null ? "" : "Air: " + weather.air + "°C"],
    ["drop", weather.humidity == null ? "" : "Humidity: " + Math.round(weather.humidity) + "%"],
    ["wind", weather.wind == null ? "" : "Wind: " + (weather.wind * 3.6).toFixed(1) + " km/h" + (weather.wind_from ? " " + weather.wind_from : "")],
    ["rain", weather.rain == null ? "" : (weather.rain > 0 ? "Rain: " + weather.rain : "Rain: DRY")],
  ] : [];
  ctx.font = "11px Arial, Helvetica, sans-serif";
  lines.forEach(function (line, index) {
    if (!line[1]) return;
    const y = 114 + index * 12;
    drawWeatherIcon(ctx, line[0], 10, y);
    ctx.fillStyle = "#f2f2f2";
    ctx.fillText(line[1], 26, y - 1);
  });
  const chosen = (focusCodes && focusCodes.length ? focusCodes : rows.slice(0, 3).map(function (row) { return row.car.code; }))
    .map(function (code) { return rows.find(function (row) { return row.car.code === code; }); })
    .filter(Boolean)
    .slice(0, 3);
  [166, 279, 392].slice(0, chosen.length).forEach(function (top, index) {
    drawDriverCard(ctx, data, chosen[index], rows, 4, top);
  });
  ctx.fillStyle = "#f2f2f2";
  ctx.font = "12px Arial, Helvetica, sans-serif";
  ["Controls:", "[SPACE] Pause/Resume", "[←/→] Rewind / FastForward", "[↑/↓] Speed +/- (0.5x, 1x, 2x, 4x)"].forEach(function (line, index) {
    ctx.fillText(line, 10, 524 + index * 13);
  });
  drawBoard(ctx, rows, focusCodes && focusCodes.length ? focusCodes[0] : (rows[0] && rows[0].car.code));
}

function drawDriverCard(ctx, data, row, rows, x, y) {
  const width = 161;
  const height = 108;
  const colour = cssColour(row.car.colour);
  ctx.fillStyle = "#000";
  ctx.fillRect(x, y, width, height);
  ctx.strokeStyle = colour;
  ctx.lineWidth = 2;
  ctx.strokeRect(x + 1, y + 1, width - 2, height - 2);
  ctx.fillStyle = colour;
  ctx.fillRect(x + 2, y + 2, width - 4, 18);
  ctx.fillStyle = "#fff";
  ctx.font = "bold 12px Arial, Helvetica, sans-serif";
  ctx.textBaseline = "top";
  ctx.fillText("Driver: " + row.car.code, x + 6, y + 4);
  const sample = row.sample;
  const ahead = rows.find(function (item) { return item.place === row.place - 1; });
  const behind = rows.find(function (item) { return item.place === row.place + 1; });
  const copy = [
    "Speed: " + (sample && sample.speed != null ? sample.speed + " km/h" : "N/A"),
    "Gear: " + (sample && sample.gear != null ? sample.gear : "N/A"),
    "DRS: " + (sample && sample.drs == null ? "N/A" : sample && sample.drs ? "ON" : "OFF"),
    ahead ? "Ahead " + gapLabel(data, row, ahead, 1) : "Ahead: N/A",
    behind ? "Behind " + gapLabel(data, row, behind, -1) : "Behind: N/A",
  ];
  ctx.fillStyle = "#f3f3f3";
  copy.forEach(function (line, index) {
    ctx.font = "10px Arial, Helvetica, sans-serif";
    if (ctx.measureText(line).width > 108) ctx.font = "9px Arial, Helvetica, sans-serif";
    ctx.fillText(line, x + 6, y + 24 + index * 13);
  });
  drawPedal(ctx, x + 116, y + 26, sample && sample.throttle != null ? sample.throttle : 0, "#00ff00");
  drawPedal(ctx, x + 140, y + 26, sample && sample.brake != null ? sample.brake : 0, "#ff2a2a");
  ctx.font = "8px Arial, Helvetica, sans-serif";
  ctx.fillStyle = "#dddddd";
  ctx.textAlign = "center";
  ctx.fillText("THR", x + 121, y + 92);
  ctx.fillText("BRK", x + 145, y + 92);
  ctx.textAlign = "left";
}

function drawPedal(ctx, x, y, percent, colour) {
  const height = 40;
  const width = 10;
  ctx.fillStyle = "#a9a9a9";
  ctx.fillRect(x, y, width, height);
  const filled = Math.max(0, Math.min(100, percent)) / 100 * height;
  ctx.fillStyle = colour;
  ctx.fillRect(x, y + height - filled, width, filled);
}

function drawBoard(ctx, rows, selected) {
  ctx.fillStyle = "#f4f4f4";
  ctx.font = "bold 13px Arial, Helvetica, sans-serif";
  ctx.textBaseline = "top";
  ctx.fillText("Leaderboard", 890, 22);
  boardHits = [];
  rows.forEach(function (row, index) {
    const y = 40 + index * 15;
    const hit = { x: 884, y: y - 1, w: 136, h: 15, code: row.car.code };
    boardHits.push(hit);
    if (row.car.code === selected) {
      ctx.fillStyle = "#505050";
      ctx.fillRect(hit.x, hit.y, hit.w, hit.h);
    }
    ctx.font = "bold 12px Arial, Helvetica, sans-serif";
    ctx.fillStyle = "#ffffff";
    ctx.fillText(String(row.place), 892, y);
    ctx.fillStyle = cssColour(row.car.colour);
    ctx.fillText(row.car.code, 914, y);
    if (row.live) {
      ctx.beginPath();
      ctx.arc(1006, y + 6, 3.4, 0, Math.PI * 2);
      ctx.fillStyle = "#00e000";
      ctx.fill();
    } else {
      ctx.fillStyle = "#e6b325";
      ctx.font = "bold 11px Arial, Helvetica, sans-serif";
      ctx.fillText("OUT", 984, y);
    }
  });
}

function drawWeatherIcon(ctx, kind, x, y) {
  ctx.save();
  ctx.translate(x, y);
  ctx.strokeStyle = "#d5d5d5";
  ctx.lineWidth = 1.1;
  ctx.beginPath();
  if (kind === "track") {
    ctx.moveTo(5, 1); ctx.lineTo(5, 8);
    ctx.moveTo(2, 3); ctx.lineTo(8, 3);
    ctx.moveTo(3, 11); ctx.bezierCurveTo(3, 9, 7, 9, 7, 11);
  } else if (kind === "air") {
    ctx.moveTo(1, 4); ctx.bezierCurveTo(4, 2, 8, 3, 9, 6);
    ctx.moveTo(1, 8); ctx.lineTo(8, 8);
  } else if (kind === "drop") {
    ctx.moveTo(5, 1); ctx.bezierCurveTo(9, 6, 9, 9, 5, 11); ctx.bezierCurveTo(1, 9, 1, 6, 5, 1);
  } else if (kind === "wind") {
    ctx.moveTo(1, 3); ctx.lineTo(7, 3); ctx.moveTo(1, 7); ctx.lineTo(9, 7);
  } else {
    ctx.moveTo(2, 4); ctx.bezierCurveTo(2, 1, 8, 1, 8, 4);
    ctx.moveTo(3, 8); ctx.lineTo(2, 11); ctx.moveTo(6, 8); ctx.lineTo(5, 11);
  }
  ctx.stroke();
  ctx.restore();
}

function strokePath(ctx, track, mask, px) {
  ctx.beginPath();
  let drawing = false;
  track.forEach(function (point, index) {
    if (mask && !mask[index]) {
      drawing = false;
      return;
    }
    const mapped = px(point[0], point[1]);
    if (!drawing) {
      ctx.moveTo(mapped[0], mapped[1]);
      drawing = true;
    } else {
      ctx.lineTo(mapped[0], mapped[1]);
    }
  });
}

function sampleAt(samples, t) {
  if (!samples || !samples.length) return null;
  const last = samples[samples.length - 1];
  if (t <= samples[0].t) return Object.assign({ live: true }, samples[0]);
  if (t >= last.t) return Object.assign({}, last, { live: t <= last.t + 12 });
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
    speed: left.speed,
    gear: left.gear,
    throttle: left.throttle,
    brake: left.brake,
    drs: left.drs,
    live: true,
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
