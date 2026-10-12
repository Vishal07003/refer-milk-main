    // 2. Cash Handover & Reconciliation Manager
cachedHandovers = [];
handoverSearchTimeout = null;

    async function loadCashHandovers() {
      const tbody = document.getElementById('handovers-table-body');
      const searchVal = document.getElementById('handover-search-input')?.value.trim() || '';
      try {
        const queryParams = new URLSearchParams();
        if (currentHandoverFilter !== 'all') queryParams.append('status', currentHandoverFilter);
        if (searchVal) queryParams.append('search', searchVal);

        const url = `/api/admin/cash-handovers/?${queryParams.toString()}`;
        const res = await fetch(url);
        const data = await res.json();
        const list = data.handovers || [];
        const summary = data.summary || {};
        cachedHandovers = list;

        // Populate reconciliation summary cards
        document.getElementById('recon-total-collected').innerText = `₹${(summary.total_cash_collected || 0).toFixed(2)}`;
        document.getElementById('recon-total-confirmed').innerText = `₹${(summary.total_cash_confirmed || 0).toFixed(2)}`;
        document.getElementById('recon-pending-balance').innerText = `₹${(summary.pending_cash_balance || 0).toFixed(2)}`;
        document.getElementById('recon-pending-tag').innerText = `${summary.pending_count || 0} submissions awaiting check`;
        document.getElementById('recon-total-discrepancy').innerText = `₹${Math.abs(summary.total_discrepancy || 0).toFixed(2)}`;
        document.getElementById('recon-discrepancy-tag').innerText = `${summary.discrepancy_count || 0} variance cases`;

        if (list.length === 0) {
          tbody.innerHTML = `<tr><td colspan="9" class="text-center py-8 text-slate-400">No cash handover records found.</td></tr>`;
          return;
        }

        tbody.innerHTML = list.map(h => {
          const isSubmitted = h.status === 'submitted';
          const isConfirmed = h.status === 'confirmed';
          const isDiscrepancy = h.status === 'discrepancy';
          const badgeClass = isConfirmed ? 'badge-verified' : isDiscrepancy ? 'badge-discrepancy' : 'badge-submitted';
          const statusText = isConfirmed ? 'Confirmed' : isDiscrepancy ? 'Discrepancy Flagged' : 'Submitted (Pending Review)';

          const discrepancyBadge = h.discrepancy_amount !== 0 ? `
            <span class="font-mono font-bold text-xs ${h.discrepancy_amount > 0 ? 'text-emerald-700' : 'text-rose-600'}">
              ${h.discrepancy_amount > 0 ? '+' : ''}₹${h.discrepancy_amount.toFixed(2)}
            </span>
          ` : `<span class="text-slate-400 font-mono text-xs">₹0.00 (Match)</span>`;

          return `
            <tr class="hover:bg-slate-50 transition">
              <td class="py-3 px-4">
                <div class="font-bold text-slate-900">#${h.id}</div>
                <div class="text-[10px] text-slate-400">Ref ID</div>
              </td>
              <td class="py-3 px-4 font-semibold text-slate-800">
                ${escapeHtml(h.delivery_boy_name)}
                <div class="text-[11px] text-slate-400 font-mono">${h.delivery_boy_mobile}</div>
                <div class="text-[10px] text-amber-700 font-semibold mt-0.5">Bal in Hand: ₹${h.partner_pending_balance.toFixed(2)}</div>
              </td>
              <td class="py-3 px-4 font-bold text-slate-900 text-sm">
                ₹${h.submitted_amount.toFixed(2)}
                ${h.delivery_notes ? `<div class="text-[10px] text-slate-500 italic max-w-xs truncate mt-0.5">"${escapeHtml(h.delivery_notes)}"</div>` : ''}
              </td>
              <td class="py-3 px-4 font-bold text-sm ${h.received_amount !== null ? 'text-emerald-800' : 'text-slate-400'}">
                ${h.received_amount !== null ? `₹${h.received_amount.toFixed(2)}` : '—'}
              </td>
              <td class="py-3 px-4">
                ${h.received_amount !== null ? discrepancyBadge : '<span class="text-slate-400">—</span>'}
              </td>
              <td class="py-3 px-4">
                <span class="px-2.5 py-0.5 rounded-full text-[11px] font-semibold ${badgeClass}">
                  ${statusText}
                </span>
              </td>
              <td class="py-3 px-4 text-slate-600 text-[11px]">${h.submitted_at}</td>
              <td class="py-3 px-4 text-[11px] text-slate-700">
                <div class="font-medium">${escapeHtml(h.confirmed_by_name || '—')}</div>
                ${h.admin_notes ? `<div class="text-[10px] text-slate-500 italic truncate max-w-xs mt-0.5">${escapeHtml(h.admin_notes)}</div>` : ''}
              </td>
              <td class="py-3 px-4 text-right space-x-1 whitespace-nowrap">
                ${isSubmitted ? `
                  <button onclick="openConfirmHandoverModal(${JSON.stringify(h).replace(/"/g, '&quot;')})" class="px-3 py-1.5 rounded-lg bg-brand hover:bg-brand-dark text-white font-semibold text-xs transition shadow-xs">
                    Confirm Cash
                  </button>
                ` : `
                  <button onclick="openConfirmHandoverModal(${JSON.stringify(h).replace(/"/g, '&quot;')})" class="px-2.5 py-1 rounded-lg border border-slate-200 text-slate-600 hover:bg-slate-100 font-medium text-xs transition">
                    Edit Count
                  </button>
                `}
                <button onclick="inspectPartnerCollections(${h.delivery_boy_id}, '${escapeHtml(h.delivery_boy_name)}', '${h.delivery_boy_mobile}')" class="px-2 py-1 rounded-lg bg-amber-50 hover:bg-amber-100 text-amber-800 border border-amber-200 font-semibold text-[11px] transition" title="Inspect individual collections">
                  Audit Drops
                </button>
              </td>
            </tr>
          `;
        }).join('');
        lucide.createIcons();
      } catch (err) {
        tbody.innerHTML = `<tr><td colspan="9" class="text-center py-6 text-red-500">Error loading handovers.</td></tr>`;
      }
    }

    function filterHandoverStatus(status) {
      currentHandoverFilter = status;
      ['all', 'submitted', 'confirmed', 'discrepancy'].forEach(s => {
        const btn = document.getElementById(`filter-handover-${s}`);
        if (btn) {
          btn.className = s === status ? 'px-3 py-1.5 text-xs font-semibold rounded-lg bg-white text-slate-800 shadow-xs' : 'px-3 py-1.5 text-xs font-medium rounded-lg text-slate-600 hover:text-slate-900';
        }
      });
      loadCashHandovers();
    }

    function debounceHandoverSearch() {
      clearTimeout(handoverSearchTimeout);
      handoverSearchTimeout = setTimeout(() => {
        loadCashHandovers();
      }, 300);
    }

    // Confirm Handover Modal Logic
    function openConfirmHandoverModal(h) {
      selectedHandoverId = h.id;
      selectedHandoverSubmitted = Number(h.submitted_amount);

      document.getElementById('handover-modal-id').innerText = `#${h.id}`;
      document.getElementById('handover-modal-partner').innerText = `${h.delivery_boy_name} (${h.delivery_boy_mobile})`;
      document.getElementById('handover-modal-submitted').innerText = `₹${selectedHandoverSubmitted.toFixed(2)}`;
      document.getElementById('handover-modal-partner-notes').innerText = h.delivery_notes || '—';

      // Prepopulate received input with submitted amount or existing received amount
      const currentReceived = h.received_amount !== null ? h.received_amount : selectedHandoverSubmitted;
      document.getElementById('handover-received-input').value = currentReceived;
      document.getElementById('handover-admin-notes').value = h.admin_notes || '';

      calculateLiveDiscrepancy();
      document.getElementById('confirm-handover-modal').classList.remove('hidden');
      lucide.createIcons();
    }

    function closeConfirmHandoverModal() {
      selectedHandoverId = null;
      document.getElementById('confirm-handover-modal').classList.add('hidden');
    }

    function calculateLiveDiscrepancy() {
      const inputVal = parseFloat(document.getElementById('handover-received-input').value);
      const diffLabel = document.getElementById('handover-live-discrepancy');
      const diffBox = document.getElementById('handover-discrepancy-box');

      if (isNaN(inputVal) || inputVal < 0) {
        diffLabel.innerText = 'Please enter a valid amount';
        diffLabel.className = 'font-bold text-xs text-rose-600';
        return;
      }

      const discrepancy = inputVal - selectedHandoverSubmitted;

      if (discrepancy === 0) {
        diffLabel.innerText = '₹0.00 (Exact Match)';
        diffLabel.className = 'font-extrabold text-xs text-emerald-700';
        diffBox.className = 'p-3 rounded-xl border border-emerald-200 bg-emerald-50/50 flex items-center justify-between text-xs';
      } else if (discrepancy > 0) {
        diffLabel.innerText = `+₹${discrepancy.toFixed(2)} (Surplus Cash Received)`;
        diffLabel.className = 'font-extrabold text-xs text-emerald-800';
        diffBox.className = 'p-3 rounded-xl border border-emerald-300 bg-emerald-100 flex items-center justify-between text-xs';
      } else {
        diffLabel.innerText = `-₹${Math.abs(discrepancy).toFixed(2)} (Shortage / Discrepancy)`;
        diffLabel.className = 'font-extrabold text-xs text-rose-700';
        diffBox.className = 'p-3 rounded-xl border border-rose-300 bg-rose-50 flex items-center justify-between text-xs';
      }
    }

    async function submitHandoverConfirmation() {
      if (!selectedHandoverId) return;
      const receivedAmount = document.getElementById('handover-received-input').value.trim();
      const adminNotes = document.getElementById('handover-admin-notes').value.trim();

      if (receivedAmount === '' || isNaN(Number(receivedAmount)) || Number(receivedAmount) < 0) {
        return showToast('Please enter a valid cash received amount', true);
      }

      try {
        const res = await fetch(`/api/admin/cash-handovers/${selectedHandoverId}/confirm/`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ received_amount: receivedAmount, admin_notes: adminNotes })
        });
        const data = await res.json();
        if (res.ok) {
          showToast(data.msg || 'Handover confirmed!');
          closeConfirmHandoverModal();
          refreshAllData();
        } else {
          showToast(data.error || 'Failed to confirm handover', true);
        }
      } catch (e) {
        showToast('Network error during confirmation', true);
      }
    }

