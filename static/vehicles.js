const PAGE_DATA = JSON.parse(document.getElementById("page-data").textContent);
let vehicles = PAGE_DATA.vehicles;
let paymentMethods = PAGE_DATA.payment_methods;

function renderVehicles() {
  const el = document.getElementById('vehicle-list');
  if (!vehicles.length) { el.innerHTML = '<div class="empty">No vehicles yet.</div>'; return; }
  el.innerHTML = vehicles.map(v => `
    <div class="item-row ${v.is_archived ? 'archived' : ''}">
      <div>
        <div class="item-name">${escapeHtml(v.name)}${v.year ? ' (' + escapeHtml(v.year) + ')' : ''}</div>
        <div class="item-meta">${escapeHtml([v.make, v.model, v.fuel_type].filter(Boolean).join(' · ')) || '—'}</div>
      </div>
      <div class="item-actions">
        <button data-id="${escapeHtml(v.id)}" class="archive-vehicle">${v.is_archived ? 'Unarchive' : 'Archive'}</button>
        <button data-id="${escapeHtml(v.id)}" class="danger delete-vehicle">Delete</button>
      </div>
    </div>
  `).join('');
  document.querySelectorAll('.archive-vehicle').forEach(btn => btn.onclick = () => archiveVehicle(btn.dataset.id));
  document.querySelectorAll('.delete-vehicle').forEach(btn => btn.onclick = () => deleteVehicle(btn.dataset.id));
}

function renderPaymentMethods() {
  const el = document.getElementById('pm-list');
  if (!paymentMethods.length) { el.innerHTML = '<div class="empty">No payment methods yet.</div>'; return; }
  el.innerHTML = paymentMethods.map(p => `
    <div class="item-row ${p.is_archived ? 'archived' : ''}">
      <div>
        <div class="item-name">${escapeHtml(p.name)}${p.card_last4 ? ' &bull;&bull;&bull;&bull;' + escapeHtml(p.card_last4) : ''}</div>
        <div class="item-meta">${escapeHtml(p.notes || '')}</div>
      </div>
      <div class="item-actions"><button data-id="${escapeHtml(p.id)}" class="archive-pm">${p.is_archived ? 'Unarchive' : 'Archive'}</button></div>
    </div>
  `).join('');
  document.querySelectorAll('.archive-pm').forEach(btn => btn.onclick = () => archivePaymentMethod(btn.dataset.id));
}

document.getElementById('v-add-btn').addEventListener('click', async () => {
  const name = document.getElementById('v-name').value.trim();
  if (!name) { alert('Enter a vehicle name.'); return; }
  await fetch('/api/vehicles', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      name, year: document.getElementById('v-year').value,
      make: document.getElementById('v-make').value, model: document.getElementById('v-model').value,
      fuel_type: document.getElementById('v-fuel-type').value, notes: document.getElementById('v-notes').value,
    }),
  });
  ['v-name', 'v-year', 'v-make', 'v-model', 'v-fuel-type', 'v-notes'].forEach(id => document.getElementById(id).value = '');
  await refreshVehicles();
});

document.getElementById('pm-add-btn').addEventListener('click', async () => {
  const name = document.getElementById('pm-name').value.trim();
  if (!name) { alert('Enter a payment method name.'); return; }
  await fetch('/api/payment-methods', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      name, notes: document.getElementById('pm-notes').value,
      card_last4: document.getElementById('pm-last4').value,
    }),
  });
  ['pm-name', 'pm-notes', 'pm-last4'].forEach(id => document.getElementById(id).value = '');
  await refreshPaymentMethods();
});

async function archiveVehicle(id) {
  const v = vehicles.find(v => String(v.id) === String(id));
  await fetch(`/api/vehicles/${id}/archive`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ archived: !v.is_archived }) });
  await refreshVehicles();
}
async function deleteVehicle(id) {
  if (!confirm('Delete this vehicle? Only works if it has no records — otherwise archive it.')) return;
  const res = await fetch(`/api/vehicles/${id}/delete`, { method: 'POST' });
  if (!res.ok) { const data = await res.json(); alert(data.error || 'Could not delete.'); return; }
  await refreshVehicles();
}
async function archivePaymentMethod(id) {
  const p = paymentMethods.find(p => String(p.id) === String(id));
  await fetch(`/api/payment-methods/${id}/archive`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ archived: !p.is_archived }) });
  await refreshPaymentMethods();
}

async function refreshVehicles() {
  const res = await fetch('/api/vehicles');
  const data = await res.json();
  vehicles = data.vehicles;
  renderVehicles();
}
async function refreshPaymentMethods() {
  const res = await fetch('/api/payment-methods');
  const data = await res.json();
  paymentMethods = data.payment_methods;
  renderPaymentMethods();
}

renderVehicles();
renderPaymentMethods();
