export function formatCount(value) {
  const number = Number(value || 0);
  return new Intl.NumberFormat('ru-RU').format(number);
}

export function formatBytes(bytes) {
  const number = Number(bytes || 0);
  if (number < 1024) return `${number} B`;
  const units = ['KB', 'MB', 'GB', 'TB'];
  let value = number / 1024;
  let unit = units[0];

  for (let index = 1; index < units.length && value >= 1024; index += 1) {
    value /= 1024;
    unit = units[index];
  }

  return `${value.toFixed(value >= 10 ? 0 : 1)} ${unit}`;
}
