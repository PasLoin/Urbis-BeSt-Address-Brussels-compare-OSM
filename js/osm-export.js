export function extractInspireId(raw) {
  if (!raw) return null;
  const m = String(raw).match(/(\d+)$/);
  return m ? m[1] : String(raw);
}

export function inspireUrl(raw) {
  if (!raw) return null;
  return `https://databrussels.be/id/address/${extractInspireId(raw)}`;
}

export function buildStreetTag(fr, nl) {
  const parts = [];
  if (fr) parts.push(fr);
  if (nl && nl !== fr) parts.push(nl);
  return parts.join(' - ');
}

export function escapeXml(s) {
  if (!s) return '';
  return String(s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&apos;');
}

export function generateOsmXml(features) {
  let xml = '<?xml version="1.0" encoding="UTF-8"?>\n<osm version="0.6" generator="UrbIS-Sync">\n';
  features.forEach((f, i) => {
    const p = f.properties || f;
    const lng = f.lng || (f.geometry && f.geometry.coordinates[0]);
    const lat = f.lat || (f.geometry && f.geometry.coordinates[1]);
    const street = buildStreetTag(p.STRNAMEFRE, p.STRNAMEDUT);
    const id = extractInspireId(p.INSPIRE_ID);
    xml += `  <node id="-${i + 1}" lat="${lat}" lon="${lng}" version="0" changeset="0">\n`;
    if (p.POLICENUM) xml += `    <tag k="addr:housenumber" v="${escapeXml(p.POLICENUM)}"/>\n`;
    if (street) xml += `    <tag k="addr:street" v="${escapeXml(street)}"/>\n`;
    if (id) xml += `    <tag k="ref:databrussels" v="${escapeXml(id)}"/>\n`;
    xml += '  </node>\n';
  });
  xml += '</osm>\n';
  return xml;
}

export function downloadOsmXml(features, filename) {
  const blob = new Blob([generateOsmXml(features)], { type: 'application/xml' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename || 'addresses.osm';
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}
