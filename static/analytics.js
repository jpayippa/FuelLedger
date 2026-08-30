const YEAR_COLORS = ['var(--accent)', 'var(--orange)', 'var(--aqua)', 'var(--yellow)'];
const tooltip = document.getElementById('tooltip');

function showTooltip(x, y, value, label) {
  document.getElementById('tt-value').textContent = value;
  document.getElementById('tt-label').textContent = label;
  tooltip.style.left = (x + 14) + 'px';
  tooltip.style.top = (y + 14) + 'px';
  tooltip.style.display = 'block';
}
function hideTooltip() { tooltip.style.display = 'none'; }

function money(cents) { return '$' + (cents / 100).toFixed(2); }

function renderBarChart(containerId, items, { labelFn, valueFn, color, valueFmt }) {
  const container = document.getElementById(containerId);
  const width = 640, height = 220, padLeft = 46, padBottom = 28, padTop = 12, padRight = 10;
  const plotW = width - padLeft - padRight;
  const plotH = height - padTop - padBottom;
  const max = Math.max(1, ...items.map(valueFn));
  const slot = plotW / Math.max(items.length, 1);
  const barW = Math.max(2, slot * 0.6);

  let grid = '', bars = '', labels = '';
  for (let f = 0; f <= 1; f += 0.25) {
    const y = padTop + plotH * (1 - f);
    grid += `<line x1="${padLeft}" y1="${y}" x2="${width - padRight}" y2="${y}" stroke="var(--border-soft)" stroke-width="1"/>`;
    grid += `<text x="${padLeft - 8}" y="${y + 3}" font-size="9" fill="var(--text-muted)" text-anchor="end">${escapeHtml(valueFmt(max * f))}</text>`;
  }

  const showEvery = Math.max(1, Math.ceil(items.length / 10));
  items.forEach((d, i) => {
    const v = valueFn(d);
    const h = max > 0 ? (v / max) * plotH : 0;
    const x = padLeft + i * slot + (slot - barW) / 2;
    const y = padTop + plotH - h;
    bars += `<rect data-i="${i}" x="${x.toFixed(1)}" y="${y.toFixed(1)}" width="${barW.toFixed(1)}" height="${Math.max(h, 1).toFixed(1)}" rx="3" fill="${color}"/>`;
    if (i % showEvery === 0) {
      labels += `<text x="${(x + barW / 2).toFixed(1)}" y="${height - 8}" font-size="9" fill="var(--text-muted)" text-anchor="middle">${escapeHtml(labelFn(d))}</text>`;
    }
  });

  if (!items.length) {
    container.innerHTML = '<div class="empty">Not enough data yet.</div>';
    return;
  }

  container.innerHTML = `<svg viewBox="0 0 ${width} ${height}">${grid}${bars}${labels}</svg>`;
  const svg = container.querySelector('svg');

  svg.addEventListener('pointermove', (e) => {
    const rect = svg.getBoundingClientRect();
    const x = (e.clientX - rect.left) * (width / rect.width);
    let idx = Math.floor((x - padLeft) / slot);
    idx = Math.max(0, Math.min(items.length - 1, idx));
    svg.querySelectorAll('rect').forEach(r => r.style.opacity = 1);
    const hovered = svg.querySelector(`rect[data-i="${idx}"]`);
    if (hovered) hovered.style.opacity = '0.7';
    showTooltip(e.clientX, e.clientY, valueFmt(valueFn(items[idx])), labelFn(items[idx]));
  });
  svg.addEventListener('pointerleave', () => {
    hideTooltip();
    svg.querySelectorAll('rect').forEach(r => r.style.opacity = 1);
  });
}

function renderLineChart(containerId, items, { labelFn, valueFn, color, valueFmt }) {
  const container = document.getElementById(containerId);
  if (!items.length) {
    container.innerHTML = '<div class="empty">Not enough data yet.</div>';
    return;
  }
  const width = 640, height = 220, padLeft = 46, padBottom = 28, padTop = 12, padRight = 10;
  const plotW = width - padLeft - padRight;
  const plotH = height - padTop - padBottom;
  const values = items.map(valueFn);
  const max = Math.max(...values) * 1.05 || 1;
  const min = Math.min(...values) * 0.95;
  const range = max - min || 1;

  const points = items.map((d, i) => {
    const x = padLeft + (items.length === 1 ? plotW / 2 : (i / (items.length - 1)) * plotW);
    const y = padTop + plotH - ((valueFn(d) - min) / range) * plotH;
    return [x, y];
  });

  let grid = '';
  for (let f = 0; f <= 1; f += 0.25) {
    const y = padTop + plotH * (1 - f);
    grid += `<line x1="${padLeft}" y1="${y}" x2="${width - padRight}" y2="${y}" stroke="var(--border-soft)" stroke-width="1"/>`;
    grid += `<text x="${padLeft - 8}" y="${y + 3}" font-size="9" fill="var(--text-muted)" text-anchor="end">${escapeHtml(valueFmt(min + range * f))}</text>`;
  }

  const linePath = points.map((p, i) => (i === 0 ? 'M' : 'L') + p[0].toFixed(1) + ',' + p[1].toFixed(1)).join(' ');
  const showEvery = Math.max(1, Math.ceil(items.length / 8));
  let labels = '';
  items.forEach((d, i) => {
    if (i % showEvery === 0) {
      labels += `<text x="${points[i][0].toFixed(1)}" y="${height - 8}" font-size="9" fill="var(--text-muted)" text-anchor="middle">${escapeHtml(labelFn(d))}</text>`;
    }
  });

  const dots = points.map((p, i) => `<circle data-i="${i}" cx="${p[0].toFixed(1)}" cy="${p[1].toFixed(1)}" r="3" fill="${color}"/>`).join('');
  const hitAreas = points.map((p, i) => `<circle data-i="${i}" cx="${p[0].toFixed(1)}" cy="${p[1].toFixed(1)}" r="14" fill="transparent"/>`).join('');

  container.innerHTML = `<svg viewBox="0 0 ${width} ${height}">${grid}<path d="${linePath}" fill="none" stroke="${color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>${dots}${labels}${hitAreas}</svg>`;
  const svg = container.querySelector('svg');

  svg.querySelectorAll('circle[r="14"]').forEach(hit => {
    hit.addEventListener('pointerenter', (e) => {
      const i = +hit.dataset.i;
      showTooltip(e.clientX, e.clientY, valueFmt(valueFn(items[i])), labelFn(items[i]));
    });
    hit.addEventListener('pointermove', (e) => showTooltip(e.clientX, e.clientY, tooltip.querySelector('.tt-value').textContent, tooltip.querySelector('.tt-label').textContent));
    hit.addEventListener('pointerleave', hideTooltip);
  });
}

function renderYoyChart(matrix) {
  const container = document.getElementById('chart-yoy');
  const years = Object.keys(matrix);
  const legendEl = document.getElementById('yoy-legend');
  if (!years.length) {
    container.innerHTML = '<div class="empty">Not enough data yet.</div>';
    return;
  }
  const width = 640, height = 220, padLeft = 46, padBottom = 28, padTop = 12, padRight = 10;
  const plotW = width - padLeft - padRight;
  const plotH = height - padTop - padBottom;
  const monthLabels = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
  const allValues = years.flatMap(y => matrix[y]);
  const max = Math.max(1, ...allValues);

  let grid = '';
  for (let f = 0; f <= 1; f += 0.25) {
    const y = padTop + plotH * (1 - f);
    grid += `<line x1="${padLeft}" y1="${y}" x2="${width - padRight}" y2="${y}" stroke="var(--border-soft)" stroke-width="1"/>`;
    grid += `<text x="${padLeft - 8}" y="${y + 3}" font-size="9" fill="var(--text-muted)" text-anchor="end">${escapeHtml(money(max * f))}</text>`;
  }
  let xLabels = '';
  monthLabels.forEach((m, i) => {
    const x = padLeft + (i / 11) * plotW;
    xLabels += `<text x="${x.toFixed(1)}" y="${height - 8}" font-size="9" fill="var(--text-muted)" text-anchor="middle">${m}</text>`;
  });

  let paths = '', allHits = '';
  years.forEach((year, yi) => {
    const color = YEAR_COLORS[yi % YEAR_COLORS.length];
    const pts = matrix[year].map((v, mi) => {
      const x = padLeft + (mi / 11) * plotW;
      const y = padTop + plotH - (v / max) * plotH;
      return [x, y];
    });
    const path = pts.map((p, i) => (i === 0 ? 'M' : 'L') + p[0].toFixed(1) + ',' + p[1].toFixed(1)).join(' ');
    paths += `<path d="${path}" fill="none" stroke="${color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>`;
    pts.forEach((p, mi) => {
      allHits += `<circle data-year="${escapeHtml(year)}" data-month="${mi}" cx="${p[0].toFixed(1)}" cy="${p[1].toFixed(1)}" r="10" fill="transparent"/>`;
    });
  });

  container.innerHTML = `<svg viewBox="0 0 ${width} ${height}">${grid}${paths}${xLabels}${allHits}</svg>`;
  container.appendChild(legendEl);
  legendEl.innerHTML = years.map((y, i) => `<span class="legend-item"><span class="legend-swatch" style="background:${YEAR_COLORS[i % YEAR_COLORS.length]}"></span>${escapeHtml(y)}</span>`).join('');

  const svg = container.querySelector('svg');
  svg.querySelectorAll('circle').forEach(hit => {
    hit.addEventListener('pointerenter', (e) => {
      const year = hit.dataset.year, mi = +hit.dataset.month;
      showTooltip(e.clientX, e.clientY, money(matrix[year][mi]), `${monthLabels[mi]} ${year}`);
    });
    hit.addEventListener('pointermove', (e) => {
      tooltip.style.left = (e.clientX + 14) + 'px';
      tooltip.style.top = (e.clientY + 14) + 'px';
    });
    hit.addEventListener('pointerleave', hideTooltip);
  });
}

function renderStats(stats) {
  const el = document.getElementById('stats');
  el.innerHTML = `
    <div class="stat"><div class="label">Fuel total</div><div class="value">$${stats.total.toFixed(2)}</div></div>
    <div class="stat"><div class="label">This month</div><div class="value">$${stats.this_month.toFixed(2)}</div></div>
    <div class="stat"><div class="label">Average fill</div><div class="value">$${stats.avg_fill.toFixed(2)}</div></div>
    <div class="stat"><div class="label">Avg price/unit</div><div class="value">${stats.avg_price_per_unit != null ? '$' + stats.avg_price_per_unit.toFixed(3) : '—'}</div></div>
    <div class="stat"><div class="label">Maintenance total</div><div class="value">$${stats.maintenance_total.toFixed(2)}</div></div>
    <div class="stat"><div class="label">Cost / km</div><div class="value">${stats.cost_per_km != null ? '$' + stats.cost_per_km.toFixed(3) : '—'}</div></div>
  `;
}

function renderPerVehicle(perVehicle) {
  const section = document.getElementById('per-vehicle-section');
  if (!perVehicle) { section.style.display = 'none'; return; }
  section.style.display = 'block';
  document.getElementById('per-vehicle-body').innerHTML = perVehicle.map(v => `
    <tr>
      <td>${escapeHtml(v.vehicle)}</td>
      <td>${money(v.fuel_total_cents)}</td>
      <td>${money(v.maintenance_total_cents)}</td>
      <td>${money(v.combined_total_cents)}</td>
      <td>${money(v.avg_fill_cents)}</td>
      <td>${v.cost_per_km != null ? '$' + v.cost_per_km.toFixed(3) : '—'}</td>
    </tr>
  `).join('');
}

function renderMaintenanceChart(items) {
  renderBarChart('chart-maintenance', items, {
    labelFn: d => d.category.length > 10 ? d.category.slice(0, 9) + '…' : d.category,
    valueFn: d => d.total_cents,
    color: 'var(--orange)',
    valueFmt: money,
  });
}

function monthPeriodLabel(period) {
  const [y, m] = period.split('-');
  const names = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
  return `${names[parseInt(m, 10) - 1]} '${y.slice(2)}`;
}
function weekPeriodLabel(period) {
  return period.replace(/^\d{4}-W/, 'W');
}

async function load() {
  const vehicleId = document.getElementById('vehicle-filter').value;
  const qs = vehicleId ? `?vehicle_id=${vehicleId}` : '';
  const res = await fetch(`/api/analytics${qs}`);
  const data = await res.json();

  renderStats(data.stats);
  renderPerVehicle(data.per_vehicle);

  renderBarChart('chart-monthly', data.monthly, {
    labelFn: d => monthPeriodLabel(d.period),
    valueFn: d => d.total_cents,
    color: 'var(--accent)',
    valueFmt: money,
  });

  renderBarChart('chart-weekly', data.weekly, {
    labelFn: d => weekPeriodLabel(d.period),
    valueFn: d => d.total_cents,
    color: 'var(--accent)',
    valueFmt: money,
  });

  renderLineChart('chart-price', data.price_trend, {
    labelFn: d => d.date.slice(5),
    valueFn: d => d.price_per_unit,
    color: 'var(--aqua)',
    valueFmt: v => '$' + v.toFixed(3),
  });

  renderYoyChart(data.year_month_matrix);
  renderMaintenanceChart(data.maintenance_by_category);
}

document.getElementById('vehicle-filter').addEventListener('change', load);
load();
