function stashTheme() {
  const styles = getComputedStyle(document.documentElement);
  return {
    grid: styles.getPropertyValue("--border").trim() || "rgba(205, 190, 250, 0.14)",
    text: styles.getPropertyValue("--ink").trim() || "#e3e2e2",
    muted: styles.getPropertyValue("--muted").trim() || "#a6a1b3",
    surface: styles.getPropertyValue("--panel").trim() || "#1b1d1f",
    accent: styles.getPropertyValue("--accent").trim() || "#cdbefa",
  };
}

function stashResizeCanvas(canvas) {
  const rect = canvas.getBoundingClientRect();
  const dpr = window.devicePixelRatio || 1;
  canvas.width = Math.max(1, Math.floor(rect.width * dpr));
  canvas.height = Math.max(1, Math.floor(rect.height * dpr));
  const ctx = canvas.getContext("2d");
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  return { ctx, width: rect.width, height: rect.height };
}

function stashDrawLegend(container, labels, values, colors) {
  if (!container) return;
  container.innerHTML = "";
  labels.forEach((label, idx) => {
    const item = document.createElement("div");
    item.className = "legend-item";
    item.innerHTML = `
      <span><span class="legend-swatch" style="background:${colors[idx % colors.length]}"></span>${label}</span>
      <strong>${Number(values[idx]).toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</strong>
    `;
    container.appendChild(item);
  });
}

function stashDrawPieChart(canvas, labels, values, colors) {
  const theme = stashTheme();
  const total = values.reduce((sum, value) => sum + value, 0);
  const { ctx, width, height } = stashResizeCanvas(canvas);
  ctx.clearRect(0, 0, width, height);
  const cx = width / 2;
  const cy = height / 2;
  const radius = Math.min(width, height) * 0.34;
  let start = -Math.PI / 2;

  if (!total) {
    ctx.fillStyle = theme.muted;
    ctx.font = "600 14px Segoe UI, Arial";
    ctx.textAlign = "center";
    ctx.fillText("No data yet", cx, cy);
    return;
  }

  values.forEach((value, idx) => {
    const angle = (value / total) * Math.PI * 2;
    ctx.beginPath();
    ctx.moveTo(cx, cy);
    ctx.arc(cx, cy, radius, start, start + angle);
    ctx.closePath();
    ctx.fillStyle = colors[idx % colors.length];
    ctx.fill();
    start += angle;
  });

  ctx.beginPath();
  ctx.arc(cx, cy, radius * 0.58, 0, Math.PI * 2);
  ctx.fillStyle = theme.surface;
  ctx.fill();

  ctx.fillStyle = theme.text;
  ctx.font = "700 14px Segoe UI, Arial";
  ctx.textAlign = "center";
  ctx.fillText("Spending mix", cx, cy - 6);
  ctx.fillStyle = theme.muted;
  ctx.font = "500 11px Segoe UI, Arial";
  ctx.fillText(`${labels.length} categories`, cx, cy + 12);
}

function stashDrawBarChart(canvas, labels, values, color) {
  const theme = stashTheme();
  const { ctx, width, height } = stashResizeCanvas(canvas);
  ctx.clearRect(0, 0, width, height);
  const pad = 30;
  const chartW = width - pad * 2;
  const chartH = height - pad * 2;
  const max = Math.max(...values, 1);
  const barW = chartW / Math.max(values.length, 1);

  ctx.strokeStyle = theme.grid;
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.moveTo(pad, pad + chartH);
  ctx.lineTo(width - pad, pad + chartH);
  ctx.stroke();

  values.forEach((value, idx) => {
    const h = (value / max) * (chartH - 24);
    const x = pad + idx * barW + barW * 0.15;
    const y = pad + chartH - h;
    const w = barW * 0.7;
    ctx.fillStyle = color;
    roundRect(ctx, x, y, w, h, 10);
    ctx.fill();

    ctx.fillStyle = theme.muted;
    ctx.font = "500 10px Segoe UI, Arial";
    ctx.save();
    ctx.translate(x + w / 2, pad + chartH + 12);
    ctx.rotate(-Math.PI / 6);
    ctx.textAlign = "right";
    ctx.fillText(labels[idx], 0, 0);
    ctx.restore();
  });
}

function stashDrawLineChart(canvas, labels, values, color) {
  const theme = stashTheme();
  const { ctx, width, height } = stashResizeCanvas(canvas);
  ctx.clearRect(0, 0, width, height);
  const pad = 28;
  const chartW = width - pad * 2;
  const chartH = height - pad * 2;
  const max = Math.max(...values, 1);

  ctx.strokeStyle = theme.grid;
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.moveTo(pad, pad + chartH);
  ctx.lineTo(width - pad, pad + chartH);
  ctx.stroke();

  if (!values.length) return;

  const step = values.length === 1 ? 0 : chartW / (values.length - 1);
  ctx.strokeStyle = color;
  ctx.fillStyle = color;
  ctx.lineWidth = 3;
  ctx.beginPath();

  values.forEach((value, idx) => {
    const x = pad + idx * step;
    const y = pad + chartH - ((value / max) * (chartH - 12));
    if (idx === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
  });
  ctx.stroke();

  values.forEach((value, idx) => {
    const x = pad + idx * step;
    const y = pad + chartH - ((value / max) * (chartH - 12));
    ctx.beginPath();
    ctx.arc(x, y, 4, 0, Math.PI * 2);
    ctx.fill();
  });
}

function roundRect(ctx, x, y, width, height, radius) {
  const r = Math.min(radius, width / 2, height / 2);
  ctx.beginPath();
  ctx.moveTo(x + r, y);
  ctx.arcTo(x + width, y, x + width, y + height, r);
  ctx.arcTo(x + width, y + height, x, y + height, r);
  ctx.arcTo(x, y + height, x, y, r);
  ctx.arcTo(x, y, x + width, y, r);
  ctx.closePath();
}
