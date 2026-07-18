export const percent = (value: number, digits = 1) => `${(value * 100).toFixed(digits)}%`

export const signedPercent = (value: number, digits = 1) =>
  `${value >= 0 ? '+' : ''}${(value * 100).toFixed(digits)}pp`

export function formatDate(value: string) {
  return new Intl.DateTimeFormat(undefined, {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  }).format(new Date(value))
}

export const shortId = (value: string) => value.slice(0, 8)

export function formatPValue(value: number) {
  if (value < 0.0001) return '<0.0001'
  return value.toFixed(4)
}
