const vehicleId = parseInt(document.getElementById('timeline-card').dataset.vehicleId, 10);
const TYPE_LABELS = { fuel: 'Fuel', maintenance: 'Maintenance', odometer: 'Odometer' };

async function load() {
  const res = await fetch(`/api/timeline/${vehicleId}`);
  const data = await res.json();
  const list = document.getElementById('timeline-list');
  const empty = document.getElementById('timeline-empty');
  const progressionByKey = {};
  data.progression.forEach(p => { progressionByKey[p.date + '|' + p.odometer] = p.distance_since_prev; });

  if (!data.timeline.length) { empty.style.display = 'block'; return; }

  list.innerHTML = data.timeline.map(e => {
    const amount = e.amount_cents != null ? '$' + (e.amount_cents / 100).toFixed(2) : '';
    const dist = e.odometer != null ? progressionByKey[e.date + '|' + e.odometer] : null;
    const odoText = e.odometer != null
      ? `${e.odometer.toLocaleString()} ${dist ? '(+' + Math.round(dist).toLocaleString() + ')' : ''}`
      : '';
    return `
      <div class="entry">
        <div class="entry-dot ${escapeHtml(e.record_type)}"></div>
        <div class="entry-body">
          <div class="entry-top">
            <span class="entry-type">${escapeHtml(TYPE_LABELS[e.record_type])}</span>
            <span class="entry-date">${escapeHtml(e.date)}</span>
          </div>
          <div class="entry-desc">${escapeHtml(e.description || '-')} ${amount ? `<span class="entry-amount">${amount}</span>` : ''}</div>
          ${odoText ? `<div class="entry-odo">Odometer: ${odoText}</div>` : ''}
        </div>
      </div>
    `;
  }).join('');
}

load();
