export function fmtNum(value) {
  const n = Number(value);
  if (value == null || Number.isNaN(n)) return '--';
  if (n >= 1_000_000_000) return `${(n / 1_000_000_000).toFixed(1)}B`;
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1000).toFixed(1)}K`;
  return String(n);
}

export function fmtMs(value) {
  const ms = Number(value);
  if (value == null || Number.isNaN(ms)) return '--';
  if (ms >= 1000) return `${(ms / 1000).toFixed(1)}s`;
  return `${ms.toFixed(0)}ms`;
}

export function fmtPct(value) {
  const v = Number(value);
  if (value == null || Number.isNaN(v)) return '--';
  return `${v.toFixed(2)}%`;
}

export function unique(values) {
  return [...new Set(values.filter(Boolean))];
}
