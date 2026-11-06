import { getI18n } from './i18n.js';

export function formatNumber(value, i18n = getI18n()) {
  return new Intl.NumberFormat(i18n.locale).format(value);
}

export function formatPercent(ratio, i18n = getI18n()) {
  return new Intl.NumberFormat(i18n.locale, {
    style: 'percent',
    minimumFractionDigits: 3,
    maximumFractionDigits: 3
  }).format(ratio);
}

export function formatDate(value, { withTime = false, i18n = getI18n() } = {}) {
  if (!value) return null;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  const options = withTime
    ? { dateStyle: 'long', timeStyle: 'short', timeZone: i18n.timeZone }
    : { dateStyle: 'long', timeZone: i18n.timeZone };
  return new Intl.DateTimeFormat(i18n.locale, options).format(date);
}
