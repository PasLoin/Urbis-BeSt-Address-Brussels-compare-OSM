import { t } from './i18n.js';

export function showToast(message) {
  const toast = document.getElementById('copy-toast');
  toast.textContent = message || t('toast.copied');
  toast.style.display = 'block';
  clearTimeout(toast._timer);
  toast._timer = setTimeout(() => { toast.style.display = 'none'; }, 1500);
}
