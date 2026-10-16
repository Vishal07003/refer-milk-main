/**
 * Admin Account & Recovery Settings Module
 * DudhDairy / Refer Milk Central Hub
 *
 * Handles:
 * - Loading registered recovery contacts & verification statuses.
 * - Changing mobile number with step-by-step SMS OTP challenge.
 * - Changing recovery email with step-by-step OTP challenge.
 * - First-time setup onboarding prompt.
 * - Changing administrator password.
 */

let cachedAccountSettings = null;

async function loadAccountSettings() {
  const badgeContainer = document.getElementById('account-recovery-badge-container');
  const alertBanner = document.getElementById('account-setup-alert');
  const mobileDisplay = document.getElementById('account-mobile-display');
  const mobileStatus = document.getElementById('account-mobile-status');
  const emailDisplay = document.getElementById('account-email-display');
  const emailStatus = document.getElementById('account-email-status');

  if (!mobileDisplay) return;

  try {
    const res = await fetch('/api/admin/account/settings/');
    if (!res.ok) throw new Error('Failed to load account settings');
    const data = await res.json();
    cachedAccountSettings = data;

    // Mobile
    mobileDisplay.innerText = data.masked_mobile || 'Not Configured';
    if (data.is_mobile_verified) {
      mobileStatus.className = 'px-2.5 py-0.5 rounded-full text-[11px] font-bold bg-emerald-50 text-emerald-700 border border-emerald-200';
      mobileStatus.innerText = 'Verified';
    } else {
      mobileStatus.className = 'px-2.5 py-0.5 rounded-full text-[11px] font-bold bg-amber-50 text-amber-700 border border-amber-200';
      mobileStatus.innerText = data.mobile_number ? 'Unverified' : 'Not Set';
    }

    // Email
    emailDisplay.innerText = data.masked_email || 'Not Configured';
    if (data.is_email_verified) {
      emailStatus.className = 'px-2.5 py-0.5 rounded-full text-[11px] font-bold bg-emerald-50 text-emerald-700 border border-emerald-200';
      emailStatus.innerText = 'Verified';
    } else {
      emailStatus.className = 'px-2.5 py-0.5 rounded-full text-[11px] font-bold bg-amber-50 text-amber-700 border border-amber-200';
      emailStatus.innerText = data.email ? 'Unverified' : 'Not Set';
    }

    // Setup Status Badge & Alert Banner
    const dashReminder = document.getElementById('dash-setup-reminder-banner');
    if (data.is_setup_complete) {
      badgeContainer.innerHTML = `
        <span class="px-3 py-1 rounded-full text-xs font-bold inline-flex items-center space-x-1 bg-emerald-100 text-emerald-800 border border-emerald-200">
          <i data-lucide="shield-check" class="w-3.5 h-3.5 mr-1 text-emerald-600"></i> Setup Complete
        </span>
      `;
      if (alertBanner) alertBanner.classList.add('hidden');
      if (dashReminder) dashReminder.classList.add('hidden');
    } else {
      badgeContainer.innerHTML = `
        <span class="px-3 py-1 rounded-full text-xs font-bold inline-flex items-center space-x-1 bg-amber-100 text-amber-800 border border-amber-200">
          <i data-lucide="alert-circle" class="w-3.5 h-3.5 mr-1 text-amber-600"></i> Setup Incomplete
        </span>
      `;
      if (alertBanner) alertBanner.classList.remove('hidden');
      if (dashReminder) dashReminder.classList.remove('hidden');
    }

    if (window.lucide && typeof lucide.createIcons === 'function') {
      lucide.createIcons();
    }
  } catch (err) {
    console.error('Error loading account settings:', err);
    if (mobileDisplay) mobileDisplay.innerText = 'Error loading';
  }
}

// Open modal for mobile or email change/setup
function openChangeContactModal(type = 'mobile', isSetup = false) {
  const modal = document.getElementById('contact-change-modal');
  const modalTitle = document.getElementById('contact-modal-title');
  const modalSubtitle = document.getElementById('contact-modal-subtitle');
  const typeInput = document.getElementById('contact-change-type');
  const inputLabel = document.getElementById('contact-input-label');
  const inputPrefix = document.getElementById('contact-input-prefix');
  const inputValue = document.getElementById('contact-input-value');
  const helpText = document.getElementById('contact-input-help');

  resetContactChangeModal();
  typeInput.value = type;

  if (type === 'mobile') {
    modalTitle.innerText = isSetup ? 'Setup Administrator Mobile' : 'Update Recovery Mobile Number';
    modalSubtitle.innerText = 'A 6-digit SMS verification code will be sent to confirm ownership.';
    inputLabel.innerText = 'Mobile Number *';
    inputPrefix.classList.remove('hidden');
    inputValue.className = 'admin-input pl-12 font-mono';
    inputValue.placeholder = '98765 43210';
    helpText.innerText = 'Enter your 10-digit mobile number. Country code (+91) is handled automatically.';
  } else {
    modalTitle.innerText = isSetup ? 'Setup Recovery Email' : 'Update Recovery Email Address';
    modalSubtitle.innerText = 'A 6-digit verification code will be emailed to confirm delivery.';
    inputLabel.innerText = 'Recovery Email Address *';
    inputPrefix.classList.add('hidden');
    inputValue.className = 'admin-input font-mono';
    inputValue.placeholder = 'admin@example.com';
    helpText.innerText = 'Enter a secure administrator email accessible for emergency password resets.';
  }

  modal.classList.remove('hidden');
  if (window.lucide && typeof lucide.createIcons === 'function') {
    lucide.createIcons();
  }
}

function closeContactChangeModal() {
  const modal = document.getElementById('contact-change-modal');
  if (modal) modal.classList.add('hidden');
  resetContactChangeModal();
}

function resetContactChangeModal() {
  const step1 = document.getElementById('contact-step-1');
  const step2 = document.getElementById('contact-step-2');
  const err1 = document.getElementById('contact-step-1-error');
  const err2 = document.getElementById('contact-step-2-error');
  const inputValue = document.getElementById('contact-input-value');
  const confirmPw = document.getElementById('contact-confirm-password');
  const otpInput = document.getElementById('contact-otp-input');
  const activeId = document.getElementById('active-challenge-id');

  if (step1) step1.classList.remove('hidden');
  if (step2) step2.classList.add('hidden');
  if (err1) { err1.innerText = ''; err1.classList.add('hidden'); }
  if (err2) { err2.innerText = ''; err2.classList.add('hidden'); }
  if (inputValue) inputValue.value = '';
  if (confirmPw) confirmPw.value = '';
  if (otpInput) otpInput.value = '';
  if (activeId) activeId.value = '';
}

async function submitInitiateContactChange() {
  const type = document.getElementById('contact-change-type').value;
  const value = document.getElementById('contact-input-value').value.trim();
  const current_password = document.getElementById('contact-confirm-password').value;
  const errBox = document.getElementById('contact-step-1-error');
  const btn = document.getElementById('contact-send-code-btn');

  errBox.classList.add('hidden');
  if (!value) {
    errBox.innerText = `Please enter a valid ${type}.`;
    errBox.classList.remove('hidden');
    return;
  }
  if (!current_password) {
    errBox.innerText = 'Please enter your current administrator password to confirm authorization.';
    errBox.classList.remove('hidden');
    return;
  }

  const originalBtnHtml = btn.innerHTML;
  btn.disabled = true;
  btn.innerHTML = `<i data-lucide="loader" class="w-4 h-4 animate-spin"></i><span>Sending code...</span>`;
  if (window.lucide) lucide.createIcons();

  try {
    const res = await fetch('/api/admin/account/initiate-contact-change/', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ type, value, current_password })
    });
    const data = await res.json();

    if (!res.ok) {
      errBox.innerText = data.error || 'Failed to dispatch verification code.';
      errBox.classList.remove('hidden');
      return;
    }

    // Success -> Transition to Step 2
    document.getElementById('active-challenge-id').value = data.challenge_id;
    document.getElementById('contact-dispatch-msg').innerText = data.message || `Code dispatched to ${data.masked_target}`;
    document.getElementById('contact-step-1').classList.add('hidden');
    document.getElementById('contact-step-2').classList.remove('hidden');
    if (typeof showToast === 'function') {
      showToast(data.message || 'Verification code dispatched!');
    }
  } catch (e) {
    errBox.innerText = 'Network connection error. Please try again.';
    errBox.classList.remove('hidden');
  } finally {
    btn.disabled = false;
    btn.innerHTML = originalBtnHtml;
    if (window.lucide) lucide.createIcons();
  }
}

async function submitVerifyContactChange() {
  const challenge_id = document.getElementById('active-challenge-id').value;
  const otp = document.getElementById('contact-otp-input').value.trim();
  const errBox = document.getElementById('contact-step-2-error');
  const btn = document.getElementById('contact-verify-btn');

  errBox.classList.add('hidden');
  if (!otp || otp.length < 4) {
    errBox.innerText = 'Please enter the verification code received.';
    errBox.classList.remove('hidden');
    return;
  }

  const originalBtnHtml = btn.innerHTML;
  btn.disabled = true;
  btn.innerHTML = `<i data-lucide="loader" class="w-4 h-4 animate-spin"></i><span>Verifying...</span>`;
  if (window.lucide) lucide.createIcons();

  try {
    const res = await fetch('/api/admin/account/verify-contact-change/', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ challenge_id, otp })
    });
    const data = await res.json();

    if (!res.ok) {
      errBox.innerText = data.error || 'Verification failed. Please check the code.';
      errBox.classList.remove('hidden');
      return;
    }

    if (typeof showToast === 'function') {
      showToast(data.message || 'Contact verified and updated successfully!');
    }
    closeContactChangeModal();
    await loadAccountSettings();

    // If setup was incomplete and there is still an unverified contact, prompt next
    if (!data.is_setup_complete) {
      if (!data.is_mobile_verified) {
        setTimeout(() => openChangeContactModal('mobile', true), 600);
      } else if (!data.is_email_verified) {
        setTimeout(() => openChangeContactModal('email', true), 600);
      }
    }
  } catch (e) {
    errBox.innerText = 'Network error while verifying code.';
    errBox.classList.remove('hidden');
  } finally {
    btn.disabled = false;
    btn.innerHTML = originalBtnHtml;
    if (window.lucide) lucide.createIcons();
  }
}

// Password Change Modal
function openChangePasswordModal() {
  const modal = document.getElementById('change-password-modal');
  const errBox = document.getElementById('change-pw-error');
  document.getElementById('pw-current').value = '';
  document.getElementById('pw-new').value = '';
  document.getElementById('pw-confirm').value = '';
  errBox.innerText = '';
  errBox.classList.add('hidden');
  modal.classList.remove('hidden');
  if (window.lucide) lucide.createIcons();
}

function closeChangePasswordModal() {
  const modal = document.getElementById('change-password-modal');
  if (modal) modal.classList.add('hidden');
}

async function submitChangePassword() {
  const current_password = document.getElementById('pw-current').value;
  const new_password = document.getElementById('pw-new').value;
  const confirm_password = document.getElementById('pw-confirm').value;
  const errBox = document.getElementById('change-pw-error');
  const btn = document.getElementById('change-pw-btn');

  errBox.classList.add('hidden');

  if (!current_password || !new_password) {
    errBox.innerText = 'Please fill in both current and new passwords.';
    errBox.classList.remove('hidden');
    return;
  }

  if (new_password !== confirm_password) {
    errBox.innerText = 'New password and confirmation do not match.';
    errBox.classList.remove('hidden');
    return;
  }

  const originalBtnHtml = btn.innerHTML;
  btn.disabled = true;
  btn.innerHTML = `<i data-lucide="loader" class="w-4 h-4 animate-spin"></i><span>Updating...</span>`;
  if (window.lucide) lucide.createIcons();

  try {
    const res = await fetch('/api/admin/account/change-password/', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ current_password, new_password, confirm_password })
    });
    const data = await res.json();

    if (!res.ok) {
      errBox.innerText = data.error || 'Failed to update password.';
      errBox.classList.remove('hidden');
      return;
    }

    if (typeof showToast === 'function') {
      showToast(data.message || 'Password successfully updated!');
    }
    closeChangePasswordModal();
  } catch (e) {
    errBox.innerText = 'Network error while updating password.';
    errBox.classList.remove('hidden');
  } finally {
    btn.disabled = false;
    btn.innerHTML = originalBtnHtml;
    if (window.lucide) lucide.createIcons();
  }
}
