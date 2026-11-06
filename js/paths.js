export const SITE_ROOT = new URL('../', import.meta.url);

export function siteUrl(path) {
  return new URL(path, SITE_ROOT).href;
}
