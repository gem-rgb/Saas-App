/**
 * AJAX Utility Module — SaaS Platform
 * Provides: ajaxPost, ajaxGet, showToast, getCookie
 * Uses the native Fetch API with automatic CSRF handling.
 */

(function (window) {
  'use strict';

  /* ── Cookie reader (for Django CSRF) ─────────────────────────── */
  function getCookie(name) {
    let cookieValue = null;
    if (document.cookie && document.cookie !== '') {
      const cookies = document.cookie.split(';');
      for (let i = 0; i < cookies.length; i++) {
        const cookie = cookies[i].trim();
        if (cookie.substring(0, name.length + 1) === (name + '=')) {
          cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
          break;
        }
      }
    }
    return cookieValue;
  }

  /* ── POST helper ─────────────────────────────────────────────── */
  async function ajaxPost(url, data, options = {}) {
    const csrftoken = getCookie('csrftoken');
    const isFormData = data instanceof FormData;

    const headers = {
      'X-Requested-With': 'XMLHttpRequest',
      'X-CSRFToken': csrftoken,
    };
    if (!isFormData) {
      headers['Content-Type'] = 'application/json';
    }

    const fetchOptions = {
      method: 'POST',
      headers: headers,
      credentials: 'same-origin',
      body: isFormData ? data : JSON.stringify(data),
      ...options,
    };

    const response = await fetch(url, fetchOptions);
    const json = await response.json();
    json._status = response.status;
    return json;
  }

  /* ── GET helper ──────────────────────────────────────────────── */
  async function ajaxGet(url, options = {}) {
    const fetchOptions = {
      method: 'GET',
      headers: {
        'X-Requested-With': 'XMLHttpRequest',
        'Accept': 'application/json',
      },
      credentials: 'same-origin',
      ...options,
    };

    const response = await fetch(url, fetchOptions);
    const json = await response.json();
    json._status = response.status;
    return json;
  }

  /* ── Toast notification system ───────────────────────────────── */
  let toastContainer = null;

  function ensureToastContainer() {
    if (toastContainer && document.body.contains(toastContainer)) return;
    toastContainer = document.createElement('div');
    toastContainer.id = 'ajax-toast-container';
    toastContainer.className = 'fixed top-16 right-4 z-[9999] space-y-3 w-96 max-w-[calc(100vw-2rem)]';
    document.body.appendChild(toastContainer);
  }

  const TOAST_ICONS = {
    success: '<svg class="w-5 h-5 shrink-0" fill="currentColor" viewBox="0 0 20 20"><path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clip-rule="evenodd"></path></svg>',
    error: '<svg class="w-5 h-5 shrink-0" fill="currentColor" viewBox="0 0 20 20"><path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clip-rule="evenodd"></path></svg>',
    warning: '<svg class="w-5 h-5 shrink-0" fill="currentColor" viewBox="0 0 20 20"><path fill-rule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clip-rule="evenodd"></path></svg>',
    info: '<svg class="w-5 h-5 shrink-0" fill="currentColor" viewBox="0 0 20 20"><path fill-rule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a1 1 0 000 2v3a1 1 0 001 1h1a1 1 0 100-2v-3a1 1 0 00-1-1H9z" clip-rule="evenodd"></path></svg>',
  };

  const TOAST_STYLES = {
    success: 'bg-green-50 border-green-200 text-green-800 dark:bg-green-900/60 dark:border-green-700 dark:text-green-300',
    error:   'bg-red-50 border-red-200 text-red-800 dark:bg-red-900/60 dark:border-red-700 dark:text-red-300',
    warning: 'bg-yellow-50 border-yellow-200 text-yellow-800 dark:bg-yellow-900/60 dark:border-yellow-700 dark:text-yellow-300',
    info:    'bg-blue-50 border-blue-200 text-blue-800 dark:bg-blue-900/60 dark:border-blue-700 dark:text-blue-300',
  };

  function showToast(message, type = 'success', duration = 5000) {
    ensureToastContainer();
    type = TOAST_STYLES[type] ? type : 'info';

    const toast = document.createElement('div');
    toast.className = `flex items-center p-4 rounded-xl shadow-lg border backdrop-blur-sm transition-all duration-500 transform translate-x-full opacity-0 ${TOAST_STYLES[type]}`;
    toast.setAttribute('role', 'alert');
    toast.innerHTML = `
      <div class="mr-3">${TOAST_ICONS[type]}</div>
      <p class="text-sm font-medium flex-1">${message}</p>
      <button class="ml-3 shrink-0 opacity-50 hover:opacity-100 transition-opacity ajax-toast-close">
        <svg class="w-4 h-4" fill="currentColor" viewBox="0 0 20 20"><path fill-rule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clip-rule="evenodd"></path></svg>
      </button>
    `;

    toastContainer.appendChild(toast);

    // Slide in
    requestAnimationFrame(() => {
      toast.classList.remove('translate-x-full', 'opacity-0');
      toast.classList.add('translate-x-0', 'opacity-100');
    });

    // Dismiss handler
    const dismiss = () => {
      toast.classList.add('translate-x-full', 'opacity-0');
      setTimeout(() => toast.remove(), 500);
    };

    toast.querySelector('.ajax-toast-close').addEventListener('click', dismiss);

    if (duration > 0) {
      setTimeout(dismiss, duration);
    }

    return toast;
  }

  /* ── Inline form error display ───────────────────────────────── */
  function showFieldErrors(form, errors) {
    // Clear previous AJAX errors
    form.querySelectorAll('.ajax-field-error').forEach(el => el.remove());
    form.querySelectorAll('.ajax-error-ring').forEach(el => {
      el.classList.remove('ajax-error-ring', 'ring-2', 'ring-red-400');
    });

    for (const [field, messages] of Object.entries(errors)) {
      const input = form.querySelector(`[name="${field}"]`);
      if (!input) continue;
      input.classList.add('ajax-error-ring', 'ring-2', 'ring-red-400');
      const errorEl = document.createElement('p');
      errorEl.className = 'ajax-field-error mt-1 text-sm text-red-500 dark:text-red-400';
      errorEl.textContent = Array.isArray(messages) ? messages[0] : messages;
      input.parentElement.appendChild(errorEl);
    }
  }

  function clearFieldErrors(form) {
    form.querySelectorAll('.ajax-field-error').forEach(el => el.remove());
    form.querySelectorAll('.ajax-error-ring').forEach(el => {
      el.classList.remove('ajax-error-ring', 'ring-2', 'ring-red-400');
    });
  }

  /* ── Button loading state ────────────────────────────────────── */
  function setButtonLoading(btn, loading) {
    if (loading) {
      btn.dataset.originalText = btn.innerHTML;
      btn.disabled = true;
      btn.innerHTML = `
        <svg class="animate-spin -ml-1 mr-2 h-4 w-4 inline-block" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
          <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
          <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"></path>
        </svg>
        Processing…
      `;
    } else {
      btn.disabled = false;
      btn.innerHTML = btn.dataset.originalText || 'Submit';
    }
  }

  /* ── Debounce helper (for live search) ───────────────────────── */
  function debounce(fn, delay = 300) {
    let timer;
    return function (...args) {
      clearTimeout(timer);
      timer = setTimeout(() => fn.apply(this, args), delay);
    };
  }

  /* ── Expose to global scope ──────────────────────────────────── */
  window.SaaSAjax = {
    get: ajaxGet,
    post: ajaxPost,
    getCookie: getCookie,
    showToast: showToast,
    showFieldErrors: showFieldErrors,
    clearFieldErrors: clearFieldErrors,
    setButtonLoading: setButtonLoading,
    debounce: debounce,
  };

})(window);
