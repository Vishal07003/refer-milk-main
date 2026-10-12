// ==========================================
// Core State & Utilities
// ==========================================
window.currentStatusFilter = 'all';
window.currentHandoverFilter = 'all';
window.searchTimeout = null;
window.selectedHandoverId = null;
window.selectedHandoverSubmitted = 0;
window.collectionsChartInstance = null;
window.donutChartInstance = null;
window.cachedDeliveryBoys = [];
window.cachedCollections = [];
window.cachedHandovers = [];
window.cachedProducts = [];
window.cachedCustomers = [];
window.cachedSubscriptionPlans = [];
window.cachedSubscriptions = [];
window.cachedOrders = [];
window.cachedCategories = [];
window.cachedSettings = [];
window.currentSubStatusFilter = 'all';
window.subSearchTimeout = null;
window.currentPlanStatusFilter = 'all';
window.planSearchTimeout = null;

function toggleSidebar() {
  const sb = document.getElementById('admin-sidebar');
  const backdrop = document.getElementById('sidebar-backdrop');
  if (sb) {
    const isClosed = sb.classList.contains('-ml-64');
    if (isClosed) {
      sb.classList.remove('-ml-64');
      if (backdrop && window.innerWidth < 1024) backdrop.classList.remove('hidden');
    } else {
      sb.classList.add('-ml-64');
      if (backdrop) backdrop.classList.add('hidden');
    }
  }
}

function closeSidebarOnMobile() {
  const sb = document.getElementById('admin-sidebar');
  const backdrop = document.getElementById('sidebar-backdrop');
  if (window.innerWidth < 1024 && sb) {
    sb.classList.add('-ml-64');
    if (backdrop) backdrop.classList.add('hidden');
  }
}

function showToast(msg, isError = false) {
  const toast = document.getElementById('toast');
  const text = document.getElementById('toast-text');
  if (!toast || !text) return;
  text.innerText = msg;
  toast.classList.remove('translate-y-20', 'opacity-0');
  setTimeout(() => {
    toast.classList.add('translate-y-20', 'opacity-0');
  }, 3500);
}

function escapeHtml(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

async function refreshAllData() {
  const icon = document.getElementById('refresh-icon');
  if (icon) icon.classList.add('animate-spin');

  const tasks = [
    { name: 'loadStatsAndTrends', fn: typeof loadStatsAndTrends === 'function' ? loadStatsAndTrends : null },
    { name: 'loadCashHandovers', fn: typeof loadCashHandovers === 'function' ? loadCashHandovers : null },
    { name: 'loadOfflineCollections', fn: typeof loadOfflineCollections === 'function' ? loadOfflineCollections : null },
    { name: 'loadOrders', fn: typeof loadOrders === 'function' ? loadOrders : null },
    { name: 'loadDeliveryBoys', fn: typeof loadDeliveryBoys === 'function' ? loadDeliveryBoys : null },
    { name: 'loadCustomers', fn: typeof loadCustomers === 'function' ? loadCustomers : null },
    { name: 'loadSubscriptionPlans', fn: typeof loadSubscriptionPlans === 'function' ? loadSubscriptionPlans : null },
    { name: 'loadDeliverySlots', fn: typeof loadDeliverySlots === 'function' ? loadDeliverySlots : null },
    { name: 'loadSubscriptions', fn: typeof loadSubscriptions === 'function' ? loadSubscriptions : null },
    { name: 'loadProducts', fn: typeof loadProducts === 'function' ? loadProducts : null },
    { name: 'loadCategories', fn: typeof loadCategories === 'function' ? loadCategories : null },
    { name: 'loadReferrals', fn: typeof loadReferrals === 'function' ? loadReferrals : null },
    { name: 'loadNotifications', fn: typeof loadNotifications === 'function' ? loadNotifications : null },
    { name: 'loadSettings', fn: typeof loadSettings === 'function' ? loadSettings : null },
    { name: 'loadReports', fn: typeof loadReports === 'function' ? loadReports : null },
  ];

  try {
    const results = await Promise.allSettled(
      tasks.map(t => {
        if (!t.fn) {
          console.warn(`[refreshAllData] Function ${t.name} is not loaded or undefined.`);
          return Promise.resolve();
        }
        return Promise.resolve(t.fn()).catch(err => {
          console.error(`[refreshAllData] Error in ${t.name}:`, err);
          throw err;
        });
      })
    );
    showToast('All data synchronized with live database');
  } catch (e) {
    console.error('Refresh all error:', e);
  } finally {
    if (icon) icon.classList.remove('animate-spin');
    if (window.lucide && typeof lucide.createIcons === 'function') {
      lucide.createIcons();
    }
  }
}
