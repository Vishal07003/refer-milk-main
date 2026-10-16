    // 11. Settings & Audit Trail
cachedSettings = [];
settingsSearchTimeout = null;

    async function loadSettings() {
      if (typeof loadAccountSettings === 'function') {
        loadAccountSettings();
      }
      const tbody = document.getElementById('settings-table-body');
      const auditTbody = document.getElementById('audit-logs-table-body');
      const searchVal = document.getElementById('settings-search-input')?.value.trim() || '';

      try {
        const queryParams = new URLSearchParams();
        if (searchVal) queryParams.append('search', searchVal);

        const res = await fetch(`/api/admin/settings/?${queryParams.toString()}`);
        const data = await res.json();
        const settings = data.settings || [];
        const logs = data.audit_logs || [];
        cachedSettings = settings;

        tbody.innerHTML = settings.map(s => `
          <tr class="hover:bg-slate-50 transition">
            <td class="py-3 px-4 font-mono font-bold text-slate-900">${escapeHtml(s.key)}</td>
            <td class="py-3 px-4 font-semibold text-brand">${escapeHtml(s.value)}</td>
            <td class="py-3 px-4 text-slate-600">${escapeHtml(s.description || '—')}</td>
            <td class="py-3 px-4 text-slate-500">${s.updated_at}</td>
            <td class="py-3 px-4 text-right">
              <button onclick="openEditSettingModal('${escapeHtml(s.key)}', '${escapeHtml(s.value)}', '${escapeHtml(s.description)}')" class="p-1.5 rounded-lg border border-slate-200 text-slate-600 hover:text-brand hover:border-brand transition">
                <i data-lucide="edit" class="w-3.5 h-3.5"></i>
              </button>
            </td>
          </tr>
        `).join('');

        if (logs.length === 0) {
          auditTbody.innerHTML = `<tr><td colspan="6" class="text-center py-6 text-slate-400">No audit log entries recorded yet.</td></tr>`;
        } else {
          auditTbody.innerHTML = logs.map(l => `
            <tr class="hover:bg-slate-50 transition font-mono text-[11px]">
              <td class="py-2.5 px-3 text-slate-500">${l.created_at}</td>
              <td class="py-2.5 px-3 font-bold text-slate-800">${escapeHtml(l.user)}</td>
              <td class="py-2.5 px-3 uppercase text-brand">${escapeHtml(l.module)}</td>
              <td class="py-2.5 px-3 font-semibold text-slate-700">${escapeHtml(l.action)}</td>
              <td class="py-2.5 px-3 text-slate-500">#${escapeHtml(l.target_id || '—')}</td>
              <td class="py-2.5 px-3 text-slate-600 truncate max-w-sm">${escapeHtml(l.details)}</td>
            </tr>
          `).join('');
        }
        lucide.createIcons();
      } catch (err) {
        tbody.innerHTML = `<tr><td colspan="5" class="text-center py-6 text-red-500">Error loading settings.</td></tr>`;
      }
    }

    function debounceSettingsSearch() {
      clearTimeout(settingsSearchTimeout);
      settingsSearchTimeout = setTimeout(() => {
        loadSettings();
      }, 300);
    }

    function openEditSettingModal(key = '', val = '', desc = '') {
      document.getElementById('setting-key').value = key;
      document.getElementById('setting-key').readOnly = !!key;
      document.getElementById('setting-value').value = val;
      document.getElementById('setting-desc').value = desc;
      document.getElementById('setting-modal').classList.remove('hidden');
    }

    function closeSettingModal() {
      document.getElementById('setting-modal').classList.add('hidden');
    }

    async function submitSaveSetting() {
      const key = document.getElementById('setting-key').value.trim();
      const value = document.getElementById('setting-value').value.trim();
      const desc = document.getElementById('setting-desc').value.trim();

      if (!key || !value) return showToast('Key and value required', true);

      try {
        const res = await fetch('/api/admin/settings/', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ key, value, description: desc })
        });
        const data = await res.json();
        if (res.ok) {
          showToast(data.msg || 'Setting saved!');
          closeSettingModal();
          loadSettings();
        } else {
          showToast(data.error || 'Failed to save setting', true);
        }
      } catch (e) {
        showToast('Network error', true);
      }
    }

