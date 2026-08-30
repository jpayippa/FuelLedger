const PAGE_DATA = JSON.parse(document.getElementById("page-data").textContent);
const VEHICLES = PAGE_DATA.vehicles;
const MAINT_CATEGORIES = PAGE_DATA.maintenance_categories;
let vehicleId = null;
let paymentMethods = [];
let fuelLogs = [];
let sortState = { key: 'date', dir: 'desc' };

function centsToStr(cents) { return '$' + (cents / 100).toFixed(2); }

// ---- Tabs ----
document.querySelectorAll('.tab-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
    document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
    btn.classList.add('active');
    document.getElementById('tab-' + btn.dataset.tab).classList.add('active');
  });
});

// ---- Vehicle selection ----
const vehicleSelect = document.getElementById('vehicle-select');
if (vehicleSelect) {
  const stored = localStorage.getItem('fuelledger-vehicle');
  if (stored && VEHICLES.some(v => String(v.id) === stored)) vehicleSelect.value = stored;
  vehicleId = parseInt(vehicleSelect.value, 10);
  vehicleSelect.addEventListener('change', () => {
    vehicleId = parseInt(vehicleSelect.value, 10);
    localStorage.setItem('fuelledger-vehicle', vehicleId);
    loadAll();
  });
  updateVehicleMeta();
}

function updateVehicleMeta() {
  const v = VEHICLES.find(v => v.id === vehicleId);
  if (!v) return;
  const parts = [v.make, v.model, v.fuel_type].filter(Boolean);
  document.getElementById('vehicle-meta').textContent = parts.join(' · ');
  document.getElementById('timeline-link').href = '/timeline/' + vehicleId;
}

async function loadPaymentMethods() {
  const res = await fetch('/api/payment-methods');
  const data = await res.json();
  paymentMethods = data.payment_methods.filter(p => !p.is_archived);
  ['fuel-f-payment', 'maint-f-payment'].forEach(id => {
    const sel = document.getElementById(id);
    sel.innerHTML = '<option value="">None</option>' + paymentMethods.map(p => `<option value="${escapeHtml(p.id)}">${escapeHtml(p.name)}</option>`).join('');
  });
}

// ================= FUEL =================
const fuelPhotoInput = document.getElementById('fuel-photo-input');
const fuelScanStatus = document.getElementById('fuel-scan-status');
const fuelReview = document.getElementById('fuel-review');
const fuelThumb = document.getElementById('fuel-thumb');
const fuelFDate = document.getElementById('fuel-f-date');
const fuelFAmount = document.getElementById('fuel-f-amount');
const fuelFStation = document.getElementById('fuel-f-station');
const fuelFVolume = document.getElementById('fuel-f-volume');
const fuelFUnit = document.getElementById('fuel-f-unit');
const fuelFPrice = document.getElementById('fuel-f-price');
const fuelRawText = document.getElementById('fuel-raw-text');
const fuelScanLabel = document.getElementById('fuel-scan-label');
const fuelDupBanner = document.getElementById('fuel-dup-banner');
let fuelConfidence = {};

function setFieldConfidence(fieldId, confId, level) {
  const field = document.getElementById(fieldId);
  const tag = document.getElementById(confId);
  if (!field) return;
  field.classList.remove('conf-low', 'conf-none');
  if (level === 'low') { field.classList.add('conf-low'); tag.textContent = 'check'; }
  else if (level === 'none') { field.classList.add('conf-none'); tag.textContent = 'missing'; }
  else { tag.textContent = ''; }
}

function checkFuelDuplicate() {
  const d = fuelFDate.value, a = parseFloat(fuelFAmount.value);
  if (!d || isNaN(a)) { fuelDupBanner.classList.remove('show'); return; }
  const match = fuelLogs.find(r => r.date === d && Math.abs(r.amount - a) < 0.01);
  if (match) {
    document.getElementById('fuel-dup-text').textContent = `Possible duplicate: a $${match.amount.toFixed(2)} entry from ${match.date} already exists.`;
    fuelDupBanner.classList.add('show');
  } else fuelDupBanner.classList.remove('show');
}
fuelFDate.addEventListener('input', checkFuelDuplicate);
fuelFAmount.addEventListener('input', checkFuelDuplicate);

function applyPaymentHint(data, selectId, hintId) {
  const select = document.getElementById(selectId);
  const hintEl = document.getElementById(hintId);
  const hint = data.payment_hint || { method: null };

  if (data.matched_payment_method_id) {
    select.value = data.matched_payment_method_id;
    const label = hint.method === 'cash' ? 'Cash' : (hint.brand ? `${hint.brand} ••••${hint.card_last4}` : `••••${hint.card_last4}`);
    hintEl.textContent = `Detected ${label} — auto-selected`;
    hintEl.classList.add('matched');
  } else if (hint.method === 'card' && hint.card_last4) {
    hintEl.textContent = `Detected ${hint.brand || 'card'} ••••${hint.card_last4} — no saved payment method matches. Add one in Manage.`;
    hintEl.classList.remove('matched');
  } else if (hint.method === 'cash') {
    hintEl.textContent = `Detected cash — add a payment method named "Cash" to auto-select next time.`;
    hintEl.classList.remove('matched');
  } else {
    hintEl.textContent = '';
    hintEl.classList.remove('matched');
  }
}

fuelPhotoInput.addEventListener('change', async () => {
  const file = fuelPhotoInput.files[0];
  if (!file) return;
  fuelThumb.src = URL.createObjectURL(file);
  fuelReview.classList.remove('show');
  fuelScanStatus.classList.add('show');
  fuelScanLabel.textContent = 'Scan another receipt';

  const formData = new FormData();
  formData.append('receipt', file);
  try {
    const res = await fetch('/scan', { method: 'POST', body: formData });
    const data = await res.json();
    if (!res.ok) {
      const message = res.status === 503
        ? (data.error || 'Server is busy processing another receipt. Please try again shortly.')
        : (data.error || 'Could not read that receipt. Enter details manually.');
      alert(message);
      fuelReview.classList.add('show');
      return;
    }
    fuelFDate.value = data.date || '';
    fuelFAmount.value = data.amount != null ? data.amount.toFixed(2) : '';
    fuelFStation.value = data.station || '';
    fuelFVolume.value = data.volume != null ? data.volume : '';
    fuelFUnit.value = data.volume_unit || 'L';
    fuelFPrice.value = data.price_per_unit != null ? data.price_per_unit : '';
    fuelRawText.textContent = data.raw_text || '';
    fuelConfidence = data.confidence || {};
    setFieldConfidence('fuel-field-date', 'fuel-conf-date', fuelConfidence.date);
    setFieldConfidence('fuel-field-amount', 'fuel-conf-amount', fuelConfidence.amount);
    setFieldConfidence('fuel-field-station', 'fuel-conf-station', fuelConfidence.station);
    setFieldConfidence('fuel-field-volume', 'fuel-conf-volume', fuelConfidence.volume);
    setFieldConfidence('fuel-field-price', 'fuel-conf-price', fuelConfidence.price_per_unit);
    applyPaymentHint(data, 'fuel-f-payment', 'fuel-payment-hint');
    fuelReview.classList.add('show');
    checkFuelDuplicate();
  } catch (e) {
    alert('Could not read that receipt. Enter details manually.');
    fuelReview.classList.add('show');
  } finally {
    fuelScanStatus.classList.remove('show');
  }
});

document.getElementById('fuel-retake-btn').addEventListener('click', () => {
  fuelPhotoInput.value = '';
  fuelReview.classList.remove('show');
  fuelScanLabel.textContent = 'Scan a fuel receipt';
});

document.getElementById('fuel-save-btn').addEventListener('click', async () => {
  if (!fuelFDate.value || !fuelFAmount.value) { alert('Enter both a date and an amount.'); return; }
  const file = fuelPhotoInput.files[0];
  const formData = new FormData();
  if (file) formData.append('receipt', file);
  formData.append('vehicle_id', vehicleId);
  formData.append('date', fuelFDate.value);
  formData.append('amount', fuelFAmount.value);
  formData.append('station', fuelFStation.value);
  formData.append('volume', fuelFVolume.value);
  formData.append('volume_unit', fuelFUnit.value);
  formData.append('price_per_unit', fuelFPrice.value);
  formData.append('odometer', document.getElementById('fuel-f-odometer').value);
  formData.append('payment_method_id', document.getElementById('fuel-f-payment').value);
  formData.append('raw_text', fuelRawText.textContent);
  formData.append('confidence', JSON.stringify(fuelConfidence));

  const btn = document.getElementById('fuel-save-btn');
  btn.disabled = true; btn.textContent = 'Saving…';
  try {
    const res = await fetch('/save/fuel', { method: 'POST', body: formData });
    if (!res.ok) throw new Error();
    fuelPhotoInput.value = '';
    fuelReview.classList.remove('show');
    fuelScanLabel.textContent = 'Scan a fuel receipt';
    await loadFuel();
  } catch (e) { alert('Could not save. Please try again.'); }
  finally { btn.disabled = false; btn.textContent = 'Save'; }
});

function fuelMatchesSearch(r, q) {
  if (!q) return true;
  q = q.toLowerCase();
  return (r.station || '').toLowerCase().includes(q) || r.date.includes(q) || r.amount.toFixed(2).includes(q);
}
function fuelLowConfidence(r) {
  const c = r.confidence || {};
  return ['low', 'none'].includes(c.date) || ['low', 'none'].includes(c.amount);
}
function renderFuelTable() {
  const q = document.getElementById('fuel-search-input').value.trim();
  const rows = fuelLogs.filter(r => fuelMatchesSearch(r, q)).sort((a, b) => {
    const av = sortState.key === 'amount' ? a.amount : a.date;
    const bv = sortState.key === 'amount' ? b.amount : b.date;
    const cmp = av < bv ? -1 : av > bv ? 1 : 0;
    return sortState.dir === 'asc' ? cmp : -cmp;
  });
  const table = document.getElementById('fuel-table');
  const empty = document.getElementById('fuel-empty-state');
  if (!rows.length) { table.style.display = 'none'; empty.style.display = 'block'; return; }
  table.style.display = 'table'; empty.style.display = 'none';
  document.getElementById('fuel-table-body').innerHTML = rows.map(r => `
    <tr>
      <td>${escapeHtml(r.date)}${fuelLowConfidence(r) ? '<span class="caution-dot" title="Low-confidence OCR"></span>' : ''}</td>
      <td class="amount">$${r.amount.toFixed(2)}</td>
      <td class="station-cell">${r.station ? escapeHtml(r.station) : '-'}</td>
      <td>
        ${r.image_filename ? `<button class="view-btn" data-src="/receipts/${escapeHtml(r.image_filename)}">View</button>` : ''}
        <button class="del-btn" data-id="${escapeHtml(r.id)}" data-type="fuel">Delete</button>
      </td>
    </tr>
  `).join('');
  wireRowButtons();
}
document.querySelectorAll('#fuel-table th[data-sort]').forEach(th => {
  th.addEventListener('click', () => {
    const key = th.dataset.sort;
    sortState.dir = (sortState.key === key && sortState.dir === 'desc') ? 'asc' : 'desc';
    sortState.key = key;
    renderFuelTable();
  });
});
document.getElementById('fuel-search-input').addEventListener('input', renderFuelTable);

async function loadFuel() {
  const res = await fetch(`/api/fuel-logs?vehicle_id=${vehicleId}`);
  const data = await res.json();
  fuelLogs = data.logs;
  const total = fuelLogs.reduce((s, r) => s + r.amount_cents, 0);
  document.getElementById('total-value').textContent = centsToStr(total);
  renderFuelTable();
}

// ================= MAINTENANCE =================
const maintPhotoInput = document.getElementById('maint-photo-input');
const maintScanStatus = document.getElementById('maint-scan-status');
const maintThumb = document.getElementById('maint-thumb');

document.getElementById('maint-f-category').addEventListener('change', (e) => {
  document.getElementById('maint-field-other').style.display = e.target.value === 'Other' ? 'block' : 'none';
});

maintPhotoInput.addEventListener('change', async () => {
  const file = maintPhotoInput.files[0];
  if (!file) return;
  maintThumb.src = URL.createObjectURL(file);
  maintThumb.style.display = 'block';
  maintScanStatus.classList.add('show');
  const formData = new FormData();
  formData.append('receipt', file);
  try {
    const res = await fetch('/scan', { method: 'POST', body: formData });
    const data = await res.json();
    if (!res.ok) {
      if (res.status === 503) alert(data.error || 'Server is busy processing another receipt. Please try again shortly.');
      return;
    }
    if (data.date) document.getElementById('maint-f-date').value = data.date;
    if (data.amount != null) document.getElementById('maint-f-amount').value = data.amount.toFixed(2);
    applyPaymentHint(data, 'maint-f-payment', 'maint-payment-hint');
  } catch (e) { /* manual entry still available */ }
  finally { maintScanStatus.classList.remove('show'); }
});
document.getElementById('maint-retake-btn').addEventListener('click', () => {
  maintPhotoInput.value = '';
  maintThumb.style.display = 'none';
});

document.getElementById('maint-save-btn').addEventListener('click', async () => {
  const dateVal = document.getElementById('maint-f-date').value;
  const amountVal = document.getElementById('maint-f-amount').value;
  if (!dateVal || !amountVal) { alert('Enter both a date and a cost.'); return; }
  const file = maintPhotoInput.files[0];
  const formData = new FormData();
  if (file) formData.append('receipt', file);
  formData.append('vehicle_id', vehicleId);
  formData.append('date', dateVal);
  formData.append('amount', amountVal);
  formData.append('shop', document.getElementById('maint-f-shop').value);
  formData.append('odometer', document.getElementById('maint-f-odometer').value);
  formData.append('category', document.getElementById('maint-f-category').value);
  formData.append('category_other', document.getElementById('maint-f-category-other').value);
  formData.append('payment_method_id', document.getElementById('maint-f-payment').value);
  formData.append('notes', document.getElementById('maint-f-notes').value);

  const btn = document.getElementById('maint-save-btn');
  btn.disabled = true; btn.textContent = 'Saving…';
  try {
    const res = await fetch('/save/maintenance', { method: 'POST', body: formData });
    if (!res.ok) throw new Error();
    maintPhotoInput.value = '';
    maintThumb.style.display = 'none';
    ['maint-f-date', 'maint-f-amount', 'maint-f-shop', 'maint-f-odometer', 'maint-f-notes', 'maint-f-category-other'].forEach(id => document.getElementById(id).value = '');
    await loadMaintenance();
  } catch (e) { alert('Could not save. Please try again.'); }
  finally { btn.disabled = false; btn.textContent = 'Save'; }
});

async function loadMaintenance() {
  const res = await fetch(`/api/maintenance-logs?vehicle_id=${vehicleId}`);
  const data = await res.json();
  const table = document.getElementById('maint-table');
  const empty = document.getElementById('maint-empty-state');
  if (!data.logs.length) { table.style.display = 'none'; empty.style.display = 'block'; return; }
  table.style.display = 'table'; empty.style.display = 'none';
  document.getElementById('maint-table-body').innerHTML = data.logs.map(r => `
    <tr>
      <td>${escapeHtml(r.date)}</td>
      <td>${escapeHtml(r.category_other || r.category)}</td>
      <td class="amount">$${r.amount.toFixed(2)}</td>
      <td>${escapeHtml(r.shop || '-')}</td>
      <td>
        ${r.image_filename ? `<button class="view-btn" data-src="/receipts/${escapeHtml(r.image_filename)}">View</button>` : ''}
        <button class="del-btn" data-id="${escapeHtml(r.id)}" data-type="maintenance">Delete</button>
      </td>
    </tr>
  `).join('');
  wireRowButtons();
}

// ================= ODOMETER =================
document.getElementById('odo-save-btn').addEventListener('click', async () => {
  const dateVal = document.getElementById('odo-f-date').value;
  const reading = document.getElementById('odo-f-reading').value;
  if (!dateVal || !reading) { alert('Enter both a date and an odometer reading.'); return; }
  const res = await fetch('/save/odometer', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ vehicle_id: vehicleId, date: dateVal, odometer: reading, note: document.getElementById('odo-f-note').value }),
  });
  if (res.ok) {
    document.getElementById('odo-f-reading').value = '';
    document.getElementById('odo-f-note').value = '';
    await loadOdometer();
  } else alert('Could not save checkpoint.');
});

async function loadOdometer() {
  const res = await fetch(`/api/odometer-logs?vehicle_id=${vehicleId}`);
  const data = await res.json();
  const table = document.getElementById('odo-table');
  const empty = document.getElementById('odo-empty-state');
  if (!data.logs.length) { table.style.display = 'none'; empty.style.display = 'block'; return; }
  table.style.display = 'table'; empty.style.display = 'none';
  document.getElementById('odo-table-body').innerHTML = data.logs.map(r => `
    <tr><td>${escapeHtml(r.date)}</td><td>${r.odometer}</td><td>${escapeHtml(r.note || '-')}</td>
    <td><button class="del-btn" data-id="${escapeHtml(r.id)}" data-type="odometer">Delete</button></td></tr>
  `).join('');
  wireRowButtons();
}

// ================= Shared: delete + lightbox =================
function wireRowButtons() {
  document.querySelectorAll('.del-btn').forEach(btn => {
    btn.onclick = async () => {
      if (!confirm('Delete this entry?')) return;
      await fetch(`/delete/${btn.dataset.type}/${btn.dataset.id}`, { method: 'POST' });
      if (btn.dataset.type === 'fuel') loadFuel();
      else if (btn.dataset.type === 'maintenance') loadMaintenance();
      else loadOdometer();
    };
  });
  document.querySelectorAll('.view-btn').forEach(btn => {
    btn.onclick = () => openLightbox(btn.dataset.src);
  });
}
function openLightbox(src) {
  document.getElementById('lightbox-img').src = src;
  document.getElementById('lightbox').classList.add('show');
}
function closeLightbox() { document.getElementById('lightbox').classList.remove('show'); }
document.getElementById('lightbox-close').addEventListener('click', closeLightbox);
document.getElementById('lightbox').addEventListener('click', (e) => { if (e.target.id === 'lightbox') closeLightbox(); });
fuelThumb.addEventListener('click', () => { if (fuelThumb.src) openLightbox(fuelThumb.src); });

if ('serviceWorker' in navigator) {
  window.addEventListener('load', () => { navigator.serviceWorker.register('/static/sw.js').catch(() => {}); });
}

async function loadAll() {
  if (!vehicleId) return;
  updateVehicleMeta();
  await Promise.all([loadFuel(), loadMaintenance(), loadOdometer()]);
}

if (vehicleId) { loadPaymentMethods(); loadAll(); }
