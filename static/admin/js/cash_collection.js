    // 3. Inspect Individual Collections for Investigation
    async function inspectPartnerCollections(boyId, boyName, boyMobile) {
      const modal = document.getElementById('inspect-modal');
      const title = document.getElementById('inspect-partner-title');
      const subtitle = document.getElementById('inspect-partner-subtitle');
      const tbody = document.getElementById('inspect-table-body');

      title.innerText = `Collections Audit: ${boyName}`;
      subtitle.innerText = `Mobile: ${boyMobile} | All underlying order cash drops contributing to partner balance`;
      tbody.innerHTML = `<tr><td colspan="5" class="text-center py-6 text-slate-400">Loading audit records...</td></tr>`;
      modal.classList.remove('hidden');
      lucide.createIcons();

      try {
        const res = await fetch(`/api/admin/offline-collections/?delivery_boy_id=${boyId}`);
        const data = await res.json();
        const list = data.collections || [];

        if (list.length === 0) {
          tbody.innerHTML = `<tr><td colspan="5" class="text-center py-6 text-slate-400">No cash collections found for this partner.</td></tr>`;
          return;
        }

        tbody.innerHTML = list.map(c => `
          <tr class="hover:bg-slate-50">
            <td class="py-2.5 px-3">
              <strong class="text-slate-900">#${c.id}</strong> (Order #${c.order_id})
            </td>
            <td class="py-2.5 px-3 font-semibold text-slate-800">${escapeHtml(c.customer_name)}</td>
            <td class="py-2.5 px-3 font-bold text-slate-900">₹${c.amount.toFixed(2)}</td>
            <td class="py-2.5 px-3 text-slate-600">${c.collected_at}</td>
            <td class="py-2.5 px-3">
              <span class="px-2 py-0.5 rounded-full text-[10px] font-semibold ${c.status === 'verified' ? 'badge-verified' : 'badge-collected'}">${c.status}</span>
            </td>
          </tr>
        `).join('');
      } catch (e) {
        tbody.innerHTML = `<tr><td colspan="5" class="text-center py-6 text-red-500">Error loading audit records.</td></tr>`;
      }
    }

    function closeInspectModal() {
      document.getElementById('inspect-modal').classList.add('hidden');
    }

    function filterStatus(status) {
      currentStatusFilter = status;
      ['all', 'collected', 'verified'].forEach(s => {
        const btn = document.getElementById(`filter-status-${s}`);
        if (btn) {
          btn.className = s === status ? 'px-3 py-1.5 text-xs font-semibold rounded-lg bg-white text-slate-800 shadow-xs' : 'px-3 py-1.5 text-xs font-medium rounded-lg text-slate-600 hover:text-slate-900';
        }
      });
      loadOfflineCollections();
    }

    function debounceSearch() {
      clearTimeout(searchTimeout);
      searchTimeout = setTimeout(loadOfflineCollections, 300);
    }

    // 4. Doorstep Cash Collections Audit Log (Automatic backend validation)
    async function loadOfflineCollections() {
      const tbody = document.getElementById('collections-table-body');
      if (!tbody) return;
      const searchEl = document.getElementById('collections-search');
      const search = searchEl ? searchEl.value : '';

      try {
        const url = `/api/admin/offline-collections/?status=${currentStatusFilter}&method=cash&search=${encodeURIComponent(search)}`;
        const res = await fetch(url);
        const data = await res.json();
        const list = data.collections || [];
        cachedCollections = list;

        if (list.length === 0) {
          tbody.innerHTML = `<tr><td colspan="8" class="text-center py-8 text-slate-400">No cash collection records found.</td></tr>`;
          return;
        }

        tbody.innerHTML = list.map(c => {
          const isVerified = c.status === 'verified';
          const badgeClass = isVerified ? 'badge-verified' : 'badge-cash';
          const statusText = isVerified ? 'Verified' : 'Auto-Collected on Delivery';

          return `
            <tr class="hover:bg-slate-50 transition">
              <td class="py-3 px-4">
                <div class="font-bold text-slate-900">#${c.id}</div>
                <div class="text-[11px] text-slate-500">Order #${c.order_id}</div>
              </td>
              <td class="py-3 px-4 font-semibold text-slate-800">${escapeHtml(c.delivery_partner_name)}<div class="text-[11px] text-slate-400 font-mono">${c.delivery_partner_mobile}</div></td>
              <td class="py-3 px-4 font-semibold text-slate-800">${escapeHtml(c.customer_name)}<div class="text-[11px] text-slate-400 font-mono">${c.customer_mobile}</div></td>
              <td class="py-3 px-4 font-bold text-slate-900 text-sm">₹${c.amount.toFixed(2)}<div class="mt-0.5"><span class="px-2 py-0.5 text-[10px] rounded font-bold uppercase badge-cash">Cash at Delivery</span></div></td>
              <td class="py-3 px-4 text-slate-600">${c.collected_at}</td>
              <td class="py-3 px-4"><span class="px-2 py-0.5 rounded-full text-[11px] font-semibold ${badgeClass}">${statusText}</span></td>
              <td class="py-3 px-4 text-[11px] text-slate-600 italic max-w-xs truncate">${escapeHtml(c.notes || 'Auto-verified with backend amount')}</td>
              <td class="py-3 px-4 text-right">
                <div class="flex items-center justify-end space-x-1.5">
                  <button onclick="openCollectionAuditModal(${c.id})" class="p-1.5 rounded-lg border border-slate-200 text-slate-700 hover:text-brand hover:border-brand text-xs font-semibold transition" title="Inspect & Audit Note">
                    <i data-lucide="file-text" class="w-3.5 h-3.5"></i>
                  </button>
                  <button onclick="inspectPartnerCollections(${c.delivery_partner_id}, '${escapeHtml(c.delivery_partner_name)}', '${c.delivery_partner_mobile}')" class="px-2 py-1 rounded-lg border border-slate-200 text-slate-700 hover:bg-slate-100 font-semibold text-[11px] transition">
                    Audit Partner
                  </button>
                </div>
              </td>
            </tr>
          `;
        }).join('');
        lucide.createIcons();
      } catch (err) {
        tbody.innerHTML = `<tr><td colspan="8" class="text-center py-6 text-red-500">Error loading collections.</td></tr>`;
      }
    }


    // Modal Control: Collection Audit
    async function openCollectionAuditModal(colId) {
      document.getElementById('collection-audit-modal').classList.remove('hidden');
      document.getElementById('audit-col-id').value = colId;
      try {
        const res = await fetch(`/api/admin/offline-collections/${colId}/`);
        const data = await res.json();
        const c = data.collection;
        if (!c) return;
        document.getElementById('audit-col-order').innerText = `#${c.order_id} (${c.customer})`;
        document.getElementById('audit-col-amount').innerText = `₹${c.amount.toFixed(2)}`;
        document.getElementById('audit-col-partner').innerText = c.delivery_partner;
        document.getElementById('audit-col-status').innerText = c.status;
        document.getElementById('audit-col-notes').value = c.notes || '';
      } catch (err) {
        showToast('Error loading collection', true);
      }
    }

    function closeCollectionAuditModal() {
      document.getElementById('collection-audit-modal').classList.add('hidden');
    }

    async function submitCollectionAudit(newStatus) {
      const id = document.getElementById('audit-col-id').value;
      const notes = document.getElementById('audit-col-notes').value.trim();

      try {
        const res = await fetch(`/api/admin/offline-collections/${id}/`, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ status: newStatus, notes })
        });
        const data = await res.json();
        if (res.ok) {
          showToast(data.msg || 'Audit record updated');
          closeCollectionAuditModal();
          loadOfflineCollections();
        } else {
          showToast(data.error || 'Failed to update audit', true);
        }
      } catch (e) {
        showToast('Network error', true);
      }
    }

    // CSV Export
    function exportCollectionsCSV() {
      if (cachedCollections.length === 0) return showToast('No records to export', true);
      let csv = 'CollectionID,OrderID,PartnerName,PartnerMobile,CustomerName,CustomerMobile,PaymentMethod,Amount,Status,UTR,CollectedTime,Notes\n';
      cachedCollections.forEach(c => {
        csv += `"${c.id}","${c.order_id}","${c.delivery_partner_name}","${c.delivery_partner_mobile}","${c.customer_name}","${c.customer_mobile}","${c.payment_method}","${c.amount}","${c.status}","${c.transaction_reference}","${c.collected_at}","${c.notes}"\n`;
      });
      const blob = new Blob([csv], { type: 'text/csv' });
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.setAttribute('hidden', '');
      a.setAttribute('href', url);
      a.setAttribute('download', `DudhDairy_Offline_Collections_${new Date().toISOString().slice(0, 10)}.csv`);
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      showToast('CSV Export generated');
    }

