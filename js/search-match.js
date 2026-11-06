import { escapeHtml } from './html.js';

export function normalize(s) {
  if (!s) return '';
  return s.toLowerCase().trim()
    .normalize('NFD').replace(/[\u0300-\u036f]/g, '')
    .replace(/\s+/g, ' ');
}

export function highlight(text, query) {
  if (!text || !query) return escapeHtml(text);
  const re = new RegExp(query.trim().replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), 'gi');
  return escapeHtml(text).replace(re, m => `<span class="sr-hl">${escapeHtml(m)}</span>`);
}

export function fuzzyScore(query, text) {
  const q = normalize(query);
  const t = normalize(text);
  if (!q || !t) return 0;
  if (t === q) return 100;
  if (t.startsWith(q)) return 90;
  if (t.includes(q)) return 70;
  const qw = q.split(' ');
  const hits = qw.filter(w => w.length > 1 && t.includes(w)).length;
  if (hits === qw.length) return 60;
  return hits > 0 ? 35 + (hits / qw.length) * 20 : 0;
}

export function splitQuery(query) {
  const m = query.match(/^(.*?)[,\s]+(\d+[a-zA-Z]?)$/);
  return { street: m ? m[1] : query, number: m ? m[2] : null };
}

export function searchIndex(index, query, maxResults) {
  const { s: streets, sn: streetNorms, a: addresses } = index;
  const { street, number } = splitQuery(query);
  const numFilter = number ? number.toLowerCase() : null;
  const qNorm = normalize(street);
  const candidates = streetNorms
    .map((sn, i) => ({ i, score: fuzzyScore(qNorm, sn) }))
    .filter(x => x.score > 0)
    .sort((a, b) => b.score - a.score)
    .slice(0, numFilter ? 20 : maxResults + 5);
  if (!candidates.length) return [];
  const scoreMap = new Map(candidates.map(x => [x.i, x.score]));
  if (!numFilter) {
    const streetCoords = new Map();
    for (const [sid, , lat, lon] of addresses) {
      if (scoreMap.has(sid) && !streetCoords.has(sid)) {
        streetCoords.set(sid, [lon, lat]);
        if (streetCoords.size === candidates.length) break;
      }
    }
    return candidates
      .filter(c => streetCoords.has(c.i))
      .slice(0, maxResults)
      .map(c => ({
        label: streets[c.i],
        sub: '',
        lngLat: streetCoords.get(c.i),
        score: c.score,
        source: 'osm'
      }));
  }
  const results = [];
  const seen = new Set();
  for (const [sid, num, lat, lon] of addresses) {
    if (!scoreMap.has(sid)) continue;
    if (!num.toLowerCase().startsWith(numFilter)) continue;
    const key = `${sid}_${num}`;
    if (seen.has(key)) continue;
    seen.add(key);
    results.push({
      label: `${streets[sid]} ${num}`,
      sub: '',
      lngLat: [lon, lat],
      score: scoreMap.get(sid) + (num.toLowerCase() === numFilter ? 10 : 0),
      source: 'osm'
    });
  }
  return results.sort((a, b) => b.score - a.score).slice(0, maxResults);
}
