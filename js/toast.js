import { getI18n } from './i18n.js';

export function showToast(message, i18n = getI18n()) {
  const toast = document.getElementById('copy-toast');
  toast.textContent = message || i18n.t('toast.copied');
  toast.style.display = 'block';
  clearTimeout(toast._timer);
  toast._timer = setTimeout(() => { toast.style.display = 'none'; }, 1500);
}
