export const LOCALE = 'fr-BE';
export const TIME_ZONE = 'Europe/Brussels';

export function formatNumber(value, locale = LOCALE) {
  return new Intl.NumberFormat(locale).format(value);
}

export function formatPercent(ratio, locale = LOCALE) {
  return new Intl.NumberFormat(locale, {
    style: 'percent',
    minimumFractionDigits: 3,
    maximumFractionDigits: 3
  }).format(ratio);
}

export function formatDate(value, { withTime = false, locale = LOCALE } = {}) {
  if (!value) return null;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  const options = withTime
    ? { dateStyle: 'long', timeStyle: 'short', timeZone: TIME_ZONE }
    : { dateStyle: 'long', timeZone: TIME_ZONE };
  return new Intl.DateTimeFormat(locale, options).format(date);
}
