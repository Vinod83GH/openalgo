/**
 * Utility functions for the Positional Strategy State UI.
 * All datetime operations use IST timezone (Asia/Kolkata, UTC+5:30).
 */

/**
 * Format a number as INR currency with 2 decimal places.
 * Example: 1234.5 → "₹1,234.50"
 */
export function formatINR(value: number): string {
  return '₹' + value.toLocaleString('en-IN', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })
}

/**
 * Convert an ISO 8601 timestamp to "DD MMM YYYY HH:MM" in IST timezone.
 * Example: "2024-03-15T10:30:00Z" → "15 Mar 2024 16:00"
 */
export function formatIST(isoString: string): string {
  const date = new Date(isoString)
  const options: Intl.DateTimeFormatOptions = {
    timeZone: 'Asia/Kolkata',
    day: '2-digit',
    month: 'short',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  }
  const parts = new Intl.DateTimeFormat('en-IN', options).formatToParts(date)

  const day = parts.find(p => p.type === 'day')?.value ?? ''
  const month = parts.find(p => p.type === 'month')?.value ?? ''
  const year = parts.find(p => p.type === 'year')?.value ?? ''
  const hour = parts.find(p => p.type === 'hour')?.value ?? ''
  const minute = parts.find(p => p.type === 'minute')?.value ?? ''

  return `${day} ${month} ${year} ${hour}:${minute}`
}

/**
 * Calculate calendar days remaining from now to the end date.
 * Returns a positive integer (ceiling of difference).
 * The endDateStr is in "YYYY-MM-DD HH:MM" format, interpreted as IST.
 */
export function getDaysRemaining(endDateStr: string): number {
  // Parse "YYYY-MM-DD HH:MM" as IST by appending the IST offset
  const [datePart, timePart] = endDateStr.split(' ')
  const isoString = `${datePart}T${timePart}:00+05:30`
  const endDate = new Date(isoString)

  const now = new Date()
  const diffMs = endDate.getTime() - now.getTime()
  const diffDays = diffMs / (1000 * 60 * 60 * 24)

  return Math.ceil(diffDays)
}

/**
 * Return singular/plural day string.
 * n=1 → "1 day", n=5 → "5 days"
 */
export function pluralizeDays(n: number): string {
  return n === 1 ? '1 day' : `${n} days`
}

/**
 * Validate that a string matches "YYYY-MM-DD HH:MM" with valid components:
 * - month: 01-12
 * - day: valid for that month (accounts for leap years)
 * - hour: 00-23
 * - minute: 00-59
 */
export function isValidDatetimeFormat(value: string): boolean {
  const regex = /^(\d{4})-(\d{2})-(\d{2}) (\d{2}):(\d{2})$/
  const match = value.match(regex)
  if (!match) return false

  const year = parseInt(match[1], 10)
  const month = parseInt(match[2], 10)
  const day = parseInt(match[3], 10)
  const hour = parseInt(match[4], 10)
  const minute = parseInt(match[5], 10)

  // Validate ranges
  if (month < 1 || month > 12) return false
  if (hour < 0 || hour > 23) return false
  if (minute < 0 || minute > 59) return false

  // Validate day for the given month/year
  const daysInMonth = new Date(year, month, 0).getDate()
  if (day < 1 || day > daysInMonth) return false

  return true
}

/**
 * Validate that entry_start < entry_end < exit_dt (strictly ascending).
 * All strings are in "YYYY-MM-DD HH:MM" format (IST).
 * Returns { valid: true } on success, or { valid: false, error: "..." } identifying
 * which pair is out of order.
 */
export function isChronologicalOrder(
  start: string,
  end: string,
  exit: string
): { valid: boolean; error?: string } {
  const startDate = parseDatetimeIST(start)
  const endDate = parseDatetimeIST(end)
  const exitDate = parseDatetimeIST(exit)

  if (startDate >= endDate) {
    return { valid: false, error: 'Entry end must be after entry start' }
  }
  if (endDate >= exitDate) {
    return { valid: false, error: 'Exit must be after entry end' }
  }

  return { valid: true }
}

/**
 * Check if the datetime (YYYY-MM-DD HH:MM format, IST) is strictly after
 * the current datetime.
 */
export function isFutureDatetime(value: string): boolean {
  const date = parseDatetimeIST(value)
  const now = new Date()
  return date.getTime() > now.getTime()
}

/**
 * Helper: parse a "YYYY-MM-DD HH:MM" string as IST and return a Date object.
 */
function parseDatetimeIST(value: string): Date {
  const [datePart, timePart] = value.split(' ')
  const isoString = `${datePart}T${timePart}:00+05:30`
  return new Date(isoString)
}
