export function formatVersion(v: string | number | undefined) {
  if (!v) return '';
  const str = String(v);
  return str.toLowerCase().startsWith('v') ? str : `v${str}`;
}
