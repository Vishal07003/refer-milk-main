// ==========================================
// Reports & Ledger (Authoritative Backend Data)
// ==========================================
window.reportCurrentHandoverStatus = 'all';
window.cachedReportsData = null;

async function loadReports() {
  await populateReportPartnerDropdown();
  await loadReportsData();
}

async function populateReportPartnerDropdown() {
  const select = document.getElementById('report-filter-partner');
  if (!select) return;

  try {
    // If delivery boys are already cached in window.cachedDeliveryBoys
    let boys = window.cachedDeliveryBoys || [];
    if (boys.length === 0) {
      const res = await fetch('/api/admin/delivery-boys/');
      const data = await res.json();
      boys = data.delivery_boys || [];
      window.cachedDeliveryBoys = boys;
    }

    const currentVal = select.value;
    select.innerHTML = '<option value="all">All Delivery Partners</option>' + boys.map(b => `
      <option value="${b.id}">${escapeHtml(b.name || (b.first_name + ' ' + b.last_name).trim() || b.username)} (${b.mobile_number})</option>
    `).join('');
    select.value = currentVal || 'all';
  } catch (e) {
    console.error('Error populating partner filter:', e);
  }
}

async function loadReportsData() {
  const errorBanner = document.getElementById('reports-error-banner');
  const partnersTbody = document.getElementById('report-partners-tbody');
  const handoversTbody = document.getElementById('report-handovers-tbody');

  if (errorBanner) errorBanner.classList.add('hidden');

  const start = document.getElementById('report-filter-start')?.value || '';
  const end = document.getElementById('report-filter-end')?.value || '';
  const partnerId = document.getElementById('report-filter-partner')?.value || 'all';
  const hoStatus = window.reportCurrentHandoverStatus || 'all';

  const params = new URLSearchParams();
  if (start) params.set('start_date', start);
  if (end) params.set('end_date', end);
  if (partnerId && partnerId !== 'all') params.set('delivery_boy_id', partnerId);
  if (hoStatus && hoStatus !== 'all') params.set('status', hoStatus);

  try {
    const res = await fetch(`/api/admin/reports/?${params.toString()}`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    window.cachedReportsData = data;

    // 1. Populate Collection Summary
    const summary = data.summary || {};
    const totalCollected = Number(summary.total_cash_collected || 0);
    const todayCash = Number(summary.today_cash || 0);
    const prevUnhanded = Number(summary.previous_unhanded_cash || 0);
    const pendingHandover = Number(summary.pending_handover || 0);
    const confirmedCash = Number(summary.confirmed_cash || 0);
    const collectionsCount = Number(summary.collections_count || 0);
    const ordersCount = Number(summary.orders_count || 0);

    const elTotal = document.getElementById('report-total-collected');
    const elToday = document.getElementById('report-today-cash');
    const elPrev = document.getElementById('report-prev-unhanded');
    const elPending = document.getElementById('report-pending-handover');
    const elConfirmed = document.getElementById('report-confirmed-cash');
    const elCollCount = document.getElementById('report-collections-count');
    const elOrderCount = document.getElementById('report-orders-count');

    if (elTotal) elTotal.innerText = `₹${totalCollected.toFixed(2)}`;
    if (elToday) elToday.innerText = `₹${todayCash.toFixed(2)}`;
    if (elPrev) elPrev.innerText = `₹${prevUnhanded.toFixed(2)}`;
    if (elPending) elPending.innerText = `₹${pendingHandover.toFixed(2)}`;
    if (elConfirmed) elConfirmed.innerText = `₹${confirmedCash.toFixed(2)}`;
    if (elCollCount) elCollCount.innerText = `${collectionsCount} collections`;
    if (elOrderCount) elOrderCount.innerText = `${ordersCount}`;

    // 2. Populate Delivery Partner Breakdown Table
    const partners = data.partner_breakdown || [];
    if (partnersTbody) {
      if (partners.length === 0) {
        partnersTbody.innerHTML = `<tr><td colspan="7" class="text-center py-6 text-slate-400">No delivery partners found.</td></tr>`;
      } else {
        partnersTbody.innerHTML = partners.map(p => `
          <tr class="hover:bg-slate-50 transition">
            <td class="py-3 px-4">
              <div class="font-bold text-slate-900">${escapeHtml(p.name)}</div>
              <div class="text-[11px] text-slate-400 font-mono">${escapeHtml(p.mobile)}</div>
            </td>
            <td class="py-3 px-4 font-semibold text-slate-800">${p.orders_collected} orders</td>
            <td class="py-3 px-4 font-bold text-slate-900">₹${Number(p.cash_collected || 0).toFixed(2)}</td>
            <td class="py-3 px-4 font-bold text-emerald-800">₹${Number(p.cash_handed_over || 0).toFixed(2)}</td>
            <td class="py-3 px-4 font-bold ${p.pending_cash > 0 ? 'text-amber-800' : 'text-slate-500'}">₹${Number(p.pending_cash || 0).toFixed(2)}</td>
            <td class="py-3 px-4 text-slate-600 text-[11px]">${escapeHtml(p.last_handover)}</td>
            <td class="py-3 px-4 text-center">
              <span class="px-2 py-0.5 rounded-full text-[10px] font-semibold ${p.status === 'Active' ? 'bg-emerald-100 text-emerald-800' : 'bg-slate-100 text-slate-600'}">
                ${p.status}
              </span>
            </td>
          </tr>
        `).join('');
      }
    }

    // 3. Populate Cash Handover Breakdown Table
    const handovers = data.handovers || [];
    if (handoversTbody) {
      if (handovers.length === 0) {
        handoversTbody.innerHTML = `<tr><td colspan="7" class="text-center py-6 text-slate-400">No cash handover records matching filter.</td></tr>`;
      } else {
        handoversTbody.innerHTML = handovers.map(h => {
          const isConfirmed = h.status === 'confirmed';
          const isDiscrepancy = h.status === 'discrepancy';
          const badgeClass = isConfirmed ? 'bg-emerald-100 text-emerald-800' : isDiscrepancy ? 'bg-rose-100 text-rose-800' : 'bg-amber-100 text-amber-800';

          return `
            <tr class="hover:bg-slate-50 transition">
              <td class="py-3 px-4 font-bold text-slate-900">#${h.id}</td>
              <td class="py-3 px-4 font-semibold text-slate-800">
                ${escapeHtml(h.delivery_partner_name)}
                <div class="text-[11px] text-slate-400 font-mono">${escapeHtml(h.delivery_partner_mobile)}</div>
              </td>
              <td class="py-3 px-4 font-bold text-slate-900">₹${Number(h.submitted_amount || 0).toFixed(2)}</td>
              <td class="py-3 px-4 font-bold text-emerald-800">
                ${h.received_amount !== null ? `₹${Number(h.received_amount).toFixed(2)}` : '—'}
              </td>
              <td class="py-3 px-4 text-slate-600 text-[11px]">${escapeHtml(h.submitted_at)}</td>
              <td class="py-3 px-4 text-slate-700 text-[11px]">${escapeHtml(h.confirmed_by || '—')}</td>
              <td class="py-3 px-4">
                <span class="px-2 py-0.5 rounded-full text-[10px] font-semibold ${badgeClass}">
                  ${escapeHtml(h.status_display || h.status)}
                </span>
              </td>
            </tr>
          `;
        }).join('');
      }
    }

    if (window.lucide && typeof lucide.createIcons === 'function') {
      lucide.createIcons();
    }
  } catch (err) {
    console.error('Error loading reports data:', err);
    if (errorBanner) {
      const errText = document.getElementById('reports-error-text');
      if (errText) errText.innerText = 'Network error fetching report data. Please check connection and retry.';
      errorBanner.classList.remove('hidden');
    }
  }
}

function applyReportFilters() {
  loadReportsData();
}

function resetReportFilters() {
  const startInput = document.getElementById('report-filter-start');
  const endInput = document.getElementById('report-filter-end');
  const partnerSelect = document.getElementById('report-filter-partner');
  if (startInput) startInput.value = '';
  if (endInput) endInput.value = '';
  if (partnerSelect) partnerSelect.value = 'all';
  filterReportHandoverStatus('all');
}

function filterReportHandoverStatus(status) {
  window.reportCurrentHandoverStatus = status;
  ['all', 'submitted', 'confirmed'].forEach(s => {
    const btn = document.getElementById(`btn-rep-ho-${s}`);
    if (btn) {
      btn.className = s === status
        ? 'px-2.5 py-1 font-semibold rounded-md bg-white text-slate-800 shadow-xs'
        : 'px-2.5 py-1 font-medium rounded-md text-slate-600 hover:text-slate-900';
    }
  });
  loadReportsData();
}

function exportReportsCSV() {
  const data = window.cachedReportsData;
  if (!data || !data.partner_breakdown || data.partner_breakdown.length === 0) {
    // If not cached yet, try exportCollectionsCSV fallback or show toast
    if (typeof exportCollectionsCSV === 'function') {
      return exportCollectionsCSV();
    }
    return showToast('No report records to export', true);
  }

  const filters = data.filters || {};
  let csv = '=== REFER MILK FINANCIAL RECONCILIATION REPORT ===\n';
  csv += `Generated At:,"${new Date().toLocaleString()}"\n`;
  csv += `Date Range:,"${filters.start_date || 'All'} to ${filters.end_date || 'All'}"\n\n`;

  csv += '=== COLLECTION SUMMARY ===\n';
  const s = data.summary || {};
  csv += `Total Cash Collected,₹${(s.total_cash_collected || 0).toFixed(2)}\n`;
  csv += `Today Cash Collection,₹${(s.today_cash || 0).toFixed(2)}\n`;
  csv += `Previous Unhanded Cash,₹${(s.previous_unhanded_cash || 0).toFixed(2)}\n`;
  csv += `Total Pending Handover,₹${(s.pending_handover || 0).toFixed(2)}\n`;
  csv += `Confirmed/Reconciled Cash,₹${(s.confirmed_cash || 0).toFixed(2)}\n`;
  csv += `Cash Collections Count,${s.collections_count || 0}\n`;
  csv += `Orders Count,${s.orders_count || 0}\n\n`;

  csv += '=== DELIVERY PARTNER BREAKDOWN ===\n';
  csv += 'PartnerID,PartnerName,Mobile,OrdersCollected,CashCollected,CashHandedOver,PendingCash,LastHandover,Status\n';
  data.partner_breakdown.forEach(p => {
    csv += `"${p.id}","${p.name}","${p.mobile}","${p.orders_collected}","${p.cash_collected}","${p.cash_handed_over}","${p.pending_cash}","${p.last_handover}","${p.status}"\n`;
  });
  csv += '\n';

  csv += '=== CASH HANDOVERS ===\n';
  csv += 'HandoverID,PartnerName,PartnerMobile,SubmittedAmount,ReceivedAmount,Discrepancy,Status,SubmittedAt,ConfirmedBy\n';
  (data.handovers || []).forEach(h => {
    csv += `"${h.id}","${h.delivery_partner_name}","${h.delivery_partner_mobile}","${h.submitted_amount}","${h.received_amount !== null ? h.received_amount : ''}","${h.discrepancy_amount}","${h.status}","${h.submitted_at}","${h.confirmed_by}"\n`;
  });

  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
  const url = window.URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.setAttribute('hidden', '');
  a.setAttribute('href', url);
  a.setAttribute('download', `ReferMilk_Financial_Report_${new Date().toISOString().slice(0, 10)}.csv`);
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  showToast('Financial Report CSV exported successfully');
}

