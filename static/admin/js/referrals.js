    // 9. Referrals Management
cachedReferrals = [];
currentReferralStatusFilter = 'all';
referralSearchTimeout = null;

    async function loadReferrals() {
      const tbody = document.getElementById('referrals-table-body');
      const searchVal = document.getElementById('ref-search-input')?.value.trim() || '';

      try {
        const queryParams = new URLSearchParams();
        if (currentReferralStatusFilter !== 'all') queryParams.append('status', currentReferralStatusFilter);
        if (searchVal) queryParams.append('search', searchVal);

        const res = await fetch(`/api/admin/referrals/?${queryParams.toString()}`);
        const data = await res.json();
        const list = data.referrals || [];
        cachedReferrals = list;

        if (list.length === 0) {
          tbody.innerHTML = `<tr><td colspan="8" class="text-center py-8 text-slate-400">No referral records found matching current filters.</td></tr>`;
          return;
        }

        tbody.innerHTML = list.map(r => `
          <tr class="hover:bg-slate-50 transition">
            <td class="py-3 px-4 font-bold text-slate-900">#${r.id}</td>
            <td class="py-3 px-4 font-semibold text-slate-800">${escapeHtml(r.referrer_name)}<div class="text-[11px] text-slate-400">${r.referrer_mobile}</div></td>
            <td class="py-3 px-4 font-semibold text-slate-800">${escapeHtml(r.referred_name)}<div class="text-[11px] text-slate-400">${r.referred_mobile}</div></td>
            <td class="py-3 px-4 font-mono font-bold text-brand">${escapeHtml(r.referral_code)}</td>
            <td class="py-3 px-4 font-bold text-emerald-700">₹${r.reward_amount.toFixed(2)}</td>
            <td class="py-3 px-4">
              <span class="px-2 py-0.5 rounded-full text-[10px] font-bold ${r.status === 'successful' ? 'bg-emerald-100 text-emerald-800' : r.status === 'pending' ? 'bg-amber-100 text-amber-800' : 'bg-red-100 text-red-800'}">
                ${r.status}
              </span>
            </td>
            <td class="py-3 px-4 text-slate-500">${r.created_at}</td>
            <td class="py-3 px-4 text-right">
              <select onchange="updateReferralStatus(${r.id}, this.value)" class="text-xs bg-slate-50 border border-slate-200 rounded-lg p-1">
                <option value="successful" ${r.status === 'successful' ? 'selected' : ''}>Successful</option>
                <option value="pending" ${r.status === 'pending' ? 'selected' : ''}>Pending</option>
                <option value="failed" ${r.status === 'failed' ? 'selected' : ''}>Failed</option>
              </select>
            </td>
          </tr>
        `).join('');
        lucide.createIcons();
      } catch (err) {
        tbody.innerHTML = `<tr><td colspan="8" class="text-center py-6 text-red-500">Error loading referrals.</td></tr>`;
      }
    }

    function debounceReferralSearch() {
      clearTimeout(referralSearchTimeout);
      referralSearchTimeout = setTimeout(() => {
        loadReferrals();
      }, 300);
    }

    function filterReferralStatus(status) {
      currentReferralStatusFilter = status;
      ['all', 'successful', 'pending', 'failed'].forEach(st => {
        const btn = document.getElementById(`ref-filter-${st}`);
        if (btn) {
          if (st === status) {
            btn.className = 'px-2.5 py-1 rounded-md font-semibold bg-white text-slate-900 shadow-xs transition';
          } else {
            btn.className = 'px-2.5 py-1 rounded-md font-medium text-slate-600 hover:text-slate-900 transition';
          }
        }
      });
      loadReferrals();
    }

    async function updateReferralStatus(id, newStatus) {
      try {
        const res = await fetch('/api/admin/referrals/', {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ id, status: newStatus })
        });
        const data = await res.json();
        showToast(data.msg || 'Referral updated');
        loadReferrals();
      } catch (err) {
        showToast('Failed to update referral', true);
      }
    }

