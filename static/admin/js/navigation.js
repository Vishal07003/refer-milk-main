// ==========================================
// Navigation & Tab Switching
// ==========================================
function switchTab(tab) {
  const allTabs = ['dashboard', 'cash-handover', 'offline-payments', 'orders', 'delivery-boys', 'customers', 'subscription-plans', 'delivery-slots', 'subscriptions', 'vacations', 'products', 'categories', 'referrals', 'notifications', 'recycle-bin', 'settings', 'reports'];
  allTabs.forEach(t => {
    const content = document.getElementById(`content-${t}`);
    const btn = document.getElementById(`nav-btn-${t}`);
    if (t === tab) {
      if (content) content.classList.remove('hidden');
      if (btn) {
        btn.className = 'w-full flex items-center space-x-3 px-3 py-2.5 rounded-xl font-semibold bg-brand text-white shadow-xs transition';
      }
      if (t === 'reports' && typeof loadReports === 'function') {
        loadReports();
      }
      if (t === 'delivery-slots' && typeof loadDeliverySlots === 'function') {
        loadDeliverySlots();
      }
      if (t === 'recycle-bin' && typeof loadRecycleBin === 'function') {
        loadRecycleBin();
      }
      if (t === 'vacations' && typeof loadVacationsData === 'function') {
        loadVacationsData();
      }
    } else {
      if (content) content.classList.add('hidden');
      if (btn) {
        btn.className = 'w-full flex items-center space-x-3 px-3 py-2.5 rounded-xl font-medium text-slate-400 hover:text-white hover:bg-slate-800 transition';
      }
    }
  });
  if (typeof closeSidebarOnMobile === 'function') {
    closeSidebarOnMobile();
  }
  if (window.lucide && typeof lucide.createIcons === 'function') {
    lucide.createIcons();
  }
}
