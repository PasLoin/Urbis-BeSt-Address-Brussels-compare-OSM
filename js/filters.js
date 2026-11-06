import { STATUSES } from './statuses.js';

export const ADDRESS_LAYER = 'addresses-points';

export function initialFilterState() {
  return Object.fromEntries(STATUSES.map(s => [s.code, s.visibleByDefault]));
}

export function filterExpression(state) {
  const codes = Object.keys(state);
  const active = codes.filter(code => state[code]);
  if (active.length === 0) return ['==', 'status', '__none__'];
  if (active.length === codes.length) return null;
  return ['in', ['get', 'status'], ['literal', active]];
}

export function initFilters(map, container = document.getElementById('filters')) {
  const state = initialFilterState();

  function apply() {
    if (!map.getLayer(ADDRESS_LAYER)) return;
    map.setFilter(ADDRESS_LAYER, filterExpression(state));
  }

  container.replaceChildren(...STATUSES.map(status => {
    const label = document.createElement('label');
    label.className = 'filter-row';
    const input = document.createElement('input');
    input.type = 'checkbox';
    input.id = `f-${status.code}`;
    input.dataset.status = status.code;
    input.checked = state[status.code];
    input.addEventListener('change', e => {
      state[status.code] = e.target.checked;
      apply();
    });
    const dot = document.createElement('span');
    dot.className = 'dot';
    dot.style.background = status.color;
    label.append(input, dot, document.createTextNode(status.label));
    return label;
  }));

  return { apply };
}
