import { useI18n } from 'vue-i18n'

const UNITS = ['b', 'kb', 'mb', 'gb'] as const

const sameYear = new Intl.DateTimeFormat('ru', {
  day: 'numeric',
  month: 'short',
  hour: '2-digit',
  minute: '2-digit',
})
const otherYear = new Intl.DateTimeFormat('ru', {
  day: 'numeric',
  month: 'short',
  year: 'numeric',
  hour: '2-digit',
  minute: '2-digit',
})
const full = new Intl.DateTimeFormat('ru', { dateStyle: 'medium', timeStyle: 'short' })

/** How the UI writes sizes, lengths of time and dates. */
export function useFormat() {
  const { t } = useI18n()

  /** 1536 -> «1,5 КБ». */
  function bytes(count: number): string {
    let value = count
    let unit = 0
    while (value >= 1024 && unit < UNITS.length - 1) {
      value /= 1024
      unit += 1
    }
    const digits = unit === 0 || value >= 100 ? 0 : 1
    const number = value.toLocaleString('ru', { maximumFractionDigits: digits })
    return `${number} ${t(`units.${UNITS[unit]}`)}`
  }

  /** 3660 -> «1 час 1 минута»: how long a post takes, to the minute. */
  function duration(seconds: number): string {
    const minutes = Math.max(1, Math.round(seconds / 60))
    const hours = Math.floor(minutes / 60)
    const rest = minutes % 60
    const parts = []
    if (hours) {
      parts.push(t('units.hours', { n: hours }, hours))
    }
    if (rest || !hours) {
      parts.push(t('units.minutes', { n: rest }, rest))
    }
    return parts.join(' ')
  }

  /** 3725 -> «1:02:05»: the length of a recording. */
  function clock(seconds: number): string {
    const whole = Math.round(seconds)
    const hours = Math.floor(whole / 3600)
    const minutes = Math.floor((whole % 3600) / 60)
    const tail = String(whole % 60).padStart(2, '0')
    return hours ? `${hours}:${String(minutes).padStart(2, '0')}:${tail}` : `${minutes}:${tail}`
  }

  /** «30 сент., 21:43»; the year is added to the dates of other years. */
  function postDate(iso: string, now: Date = new Date()): string {
    const date = new Date(iso)
    return (date.getFullYear() === now.getFullYear() ? sameYear : otherYear).format(date)
  }

  function dateTime(iso: string): string {
    return full.format(new Date(iso))
  }

  return { bytes, duration, clock, postDate, dateTime }
}
