    // 8. Categories CRUD
cachedCategories = [];
currentCategoryStatusFilter = 'all';
categorySearchTimeout = null;

    async function loadCategories() {
      const tbody = document.getElementById('categories-table-body');
      const searchVal = document.getElementById('category-search-input')?.value.trim() || '';

      try {
        const queryParams = new URLSearchParams();
        if (currentCategoryStatusFilter !== 'all') queryParams.append('status', currentCategoryStatusFilter);
        if (searchVal) queryParams.append('search', searchVal);

        const res = await fetch(`/api/admin/categories/?${queryParams.toString()}`);
        const data = await res.json();
        const list = data.categories || [];
        cachedCategories = list;

        if (list.length === 0) {
          tbody.innerHTML = `<tr><td colspan="5" class="text-center py-8 text-slate-400">No categories found matching current filters.</td></tr>`;
          return;
        }

        tbody.innerHTML = list.map(c => `
          <tr class="hover:bg-slate-50 transition">
            <td class="py-3 px-4 font-bold text-slate-900">${escapeHtml(c.name)}</td>
            <td class="py-3 px-4 text-slate-600">${escapeHtml(c.description || '—')}</td>
            <td class="py-3 px-4 font-semibold text-slate-700">${c.product_count} product(s)</td>
            <td class="py-3 px-4">
              <button onclick="toggleCategoryActive(${c.id})" class="px-2 py-0.5 rounded-full text-[10px] font-bold ${c.is_active ? 'bg-emerald-100 text-emerald-800' : 'bg-slate-100 text-slate-600'}">
                ${c.is_active ? 'Active' : 'Inactive'}
              </button>
            </td>
            <td class="py-3 px-4 text-right">
              <div class="flex items-center justify-end space-x-1.5">
                <button onclick="openEditCategoryModal(${c.id})" class="p-1.5 rounded-lg border border-slate-200 text-slate-600 hover:text-blue-600 transition" title="Edit Category">
                  <i data-lucide="edit" class="w-3.5 h-3.5"></i>
                </button>
                <button onclick="deleteCategoryPrompt(${c.id}, '${escapeHtml(c.name)}', ${c.product_count})" class="p-1.5 rounded-lg border border-red-200 text-red-600 hover:bg-red-50 transition" title="Delete Category">
                  <i data-lucide="trash-2" class="w-3.5 h-3.5"></i>
                </button>
              </div>
            </td>
          </tr>
        `).join('');
        lucide.createIcons();
      } catch (err) {
        tbody.innerHTML = `<tr><td colspan="5" class="text-center py-6 text-red-500">Error loading categories.</td></tr>`;
      }
    }

    function debounceCategorySearch() {
      clearTimeout(categorySearchTimeout);
      categorySearchTimeout = setTimeout(() => {
        loadCategories();
      }, 300);
    }

    function filterCategoryStatus(status) {
      currentCategoryStatusFilter = status;
      ['all', 'active', 'inactive'].forEach(st => {
        const btn = document.getElementById(`cat-filter-${st}`);
        if (btn) {
          if (st === status) {
            btn.className = 'px-2.5 py-1 rounded-md font-semibold bg-white text-slate-900 shadow-xs transition';
          } else {
            btn.className = 'px-2.5 py-1 rounded-md font-medium text-slate-600 hover:text-slate-900 transition';
          }
        }
      });
      loadCategories();
    }

    function openCreateCategoryModal() {
      document.getElementById('cat-modal-title').innerText = 'Add Category';
      document.getElementById('cat-id').value = '';
      document.getElementById('cat-name').value = '';
      document.getElementById('cat-desc').value = '';
      document.getElementById('cat-active').checked = true;
      document.getElementById('category-modal').classList.remove('hidden');
    }

    function openEditCategoryModal(id) {
      const c = cachedCategories.find(item => item.id === id);
      if (!c) return;
      document.getElementById('cat-modal-title').innerText = 'Edit Category';
      document.getElementById('cat-id').value = c.id;
      document.getElementById('cat-name').value = c.name;
      document.getElementById('cat-desc').value = c.description || '';
      document.getElementById('cat-active').checked = !!c.is_active;
      document.getElementById('category-modal').classList.remove('hidden');
    }

    function closeCategoryModal() {
      document.getElementById('category-modal').classList.add('hidden');
    }

    async function submitSaveCategory() {
      const id = document.getElementById('cat-id').value;
      const name = document.getElementById('cat-name').value.trim();
      const desc = document.getElementById('cat-desc').value.trim();
      const isActive = document.getElementById('cat-active').checked;

      if (!name) return showToast('Category name is required', true);

      try {
        const method = id ? 'PUT' : 'POST';
        const payload = id ? { id, name, description: desc, is_active: isActive } : { name, description: desc };
        const res = await fetch('/api/admin/categories/', {
          method,
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload)
        });
        const data = await res.json();
        if (res.ok) {
          showToast(data.msg || 'Category saved!');
          closeCategoryModal();
          loadCategories();
          loadProducts();
        } else {
          showToast(data.error || 'Failed to save category', true);
        }
      } catch (e) {
        showToast('Network error', true);
      }
    }

    async function toggleCategoryActive(id) {
      try {
        const res = await fetch('/api/admin/categories/', {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ id, action: 'toggle_active' })
        });
        const data = await res.json();
        showToast(data.msg || 'Status updated');
        loadCategories();
      } catch (err) {
        showToast('Failed to update status', true);
      }
    }

    async function deleteCategoryPrompt(id, name, count) {
      if (count > 0) {
        alert(`Cannot delete category "${name}" because it contains ${count} product(s). Please reassign or delete linked products first.`);
        return;
      }
      if (!confirm(`Are you sure you want to delete category "${name}"? This action cannot be undone.`)) return;

      try {
        const res = await fetch('/api/admin/categories/', {
          method: 'DELETE',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ id })
        });
        const data = await res.json();
        if (res.ok) {
          showToast(data.msg || 'Category deleted');
          loadCategories();
        } else {
          showToast(data.error || 'Failed to delete category', true);
        }
      } catch (e) {
        showToast('Network error', true);
      }
    }

