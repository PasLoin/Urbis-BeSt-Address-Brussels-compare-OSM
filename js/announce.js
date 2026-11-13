const ANNOUNCE_DELAY = 100;

export function announce(message, doc = document) {
  const region = doc.getElementById('a11y-status');
  if (!region) return;
  clearTimeout(region._timer);
  region.textContent = '';
  region._timer = setTimeout(() => { region.textContent = message; }, ANNOUNCE_DELAY);
}
