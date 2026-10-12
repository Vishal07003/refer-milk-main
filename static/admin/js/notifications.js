    // 10. Notifications Management
cachedNotifications = [];
notifSearchTimeout = null;

    async function loadNotifications() {
      const tbody = document.getElementById('notifications-table-body');
      const typeFilter = document.getElementById('notif-type-filter')?.value || 'all';
      const searchVal = document.getElementById('notif-search-input')?.value.trim() || '';

      try {
        const queryParams = new URLSearchParams();
        if (typeFilter !== 'all') queryParams.append('type', typeFilter);
        if (searchVal) queryParams.append('search', searchVal);

        const res = await fetch(`/api/admin/notifications/?${queryParams.toString()}`);
        const data = await res.json();
        const list = data.notifications || [];
        cachedNotifications = list;

        if (list.length === 0) {
          tbody.innerHTML = `<tr><td colspan="6" class="text-center py-8 text-slate-400">No push notifications found matching current filters.</td></tr>`;
          return;
        }

        tbody.innerHTML = list.map(n => `
          <tr class="hover:bg-slate-50 transition">
            <td class="py-3 px-4 font-semibold text-slate-800">${escapeHtml(n.user_name)}<div class="text-[11px] text-slate-400 font-mono">${n.user_mobile}</div></td>
            <td class="py-3 px-4 font-bold text-slate-900">${escapeHtml(n.title)}</td>
            <td class="py-3 px-4 text-slate-600 truncate max-w-xs">${escapeHtml(n.message)}</td>
            <td class="py-3 px-4 uppercase text-[10px] font-bold text-slate-500">${n.notification_type}</td>
            <td class="py-3 px-4 text-slate-500">${n.created_at}</td>
            <td class="py-3 px-4 text-right">
              <button onclick="deleteNotification(${n.id})" class="p-1.5 rounded-lg border border-red-200 text-red-600 hover:bg-red-50 transition" title="Delete">
                <i data-lucide="trash-2" class="w-3.5 h-3.5"></i>
              </button>
            </td>
          </tr>
        `).join('');
        lucide.createIcons();
      } catch (err) {
        tbody.innerHTML = `<tr><td colspan="6" class="text-center py-6 text-red-500">Error loading notifications.</td></tr>`;
      }
    }

    function debounceNotifSearch() {
      clearTimeout(notifSearchTimeout);
      notifSearchTimeout = setTimeout(() => {
        loadNotifications();
      }, 300);
    }

    function filterNotifications() {
      loadNotifications();
    }

    function openCreateNotificationModal() {
      document.getElementById('notif-title').value = '';
      document.getElementById('notif-body').value = '';
      document.getElementById('notification-modal').classList.remove('hidden');
    }

    function closeNotificationModal() {
      document.getElementById('notification-modal').classList.add('hidden');
    }

    async function submitSendNotification() {
      const target = document.getElementById('notif-target').value;
      const title = document.getElementById('notif-title').value.trim();
      const message = document.getElementById('notif-body').value.trim();

      if (!title || !message) return showToast('Title and message are required', true);

      try {
        const res = await fetch('/api/admin/notifications/', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ target, title, message })
        });
        const data = await res.json();
        if (res.ok) {
          showToast(data.msg || 'Notification sent!');
          closeNotificationModal();
          loadNotifications();
        } else {
          showToast(data.error || 'Failed to send notification', true);
        }
      } catch (err) {
        showToast('Network error', true);
      }
    }

    async function deleteNotification(id) {
      if (!confirm('Are you sure you want to remove this notification?')) return;
      try {
        const res = await fetch('/api/admin/notifications/', {
          method: 'DELETE',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ id })
        });
        const data = await res.json();
        showToast(data.msg || 'Notification deleted');
        loadNotifications();
      } catch (err) {
        showToast('Failed to delete notification', true);
      }
    }

