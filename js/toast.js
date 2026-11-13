import { getI18n } from './i18n.js';
import { announce } from './announce.js';

export function showToast(message, i18n = getI18n()) {
  const toast = document.getElementById('copy-toast');
  const text = message || i18n.t('toast.copied');
  toast.textContent = text;
  toast.classList.add('visible');
  announce(text);
  clearTimeout(toast._timer);
  toast._timer = setTimeout(() => {
    toast.classList.remove('visible');
    toast.textContent = '';
  }, 1500);
}
