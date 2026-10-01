import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import { defineComponent, h } from 'vue'

import { useFormat } from '@/composables/format'
import { i18n } from '@/i18n'

/** The composable needs a component around it for the translations. */
function format(): ReturnType<typeof useFormat> {
  let api!: ReturnType<typeof useFormat>
  mount(
    defineComponent({
      setup() {
        api = useFormat()
        return () => h('div')
      },
    }),
    { global: { plugins: [i18n] } },
  )
  return api
}

describe('useFormat', () => {
  it('writes sizes the way people read them', () => {
    const { bytes } = format()

    expect(bytes(0)).toBe('0 Б')
    expect(bytes(512)).toBe('512 Б')
    expect(bytes(1536)).toBe('1,5 КБ')
    expect(bytes(48_211_234)).toBe('46 МБ')
    expect(bytes(150 * 1024 ** 2)).toBe('150 МБ')
    expect(bytes(5 * 1024 ** 4)).toBe(`${(5120).toLocaleString('ru')} ГБ`)
  })

  it('tells how long a post takes, in words', () => {
    const { duration } = format()

    expect(duration(20)).toBe('1 минута')
    expect(duration(120)).toBe('2 минуты')
    expect(duration(300)).toBe('5 минут')
    expect(duration(1260)).toBe('21 минута')
    expect(duration(3600)).toBe('1 час')
    expect(duration(3660)).toBe('1 час 1 минута')
    expect(duration(2 * 3600 + 12 * 60)).toBe('2 часа 12 минут')
    expect(duration(11 * 3600)).toBe('11 часов')
  })

  it('writes the length of a recording as a clock', () => {
    const { clock } = format()

    expect(clock(5)).toBe('0:05')
    expect(clock(65)).toBe('1:05')
    expect(clock(3725)).toBe('1:02:05')
    expect(clock(1834.56)).toBe('30:35')
  })

  it('leaves the year out of the dates of this year', () => {
    const { postDate } = format()
    const now = new Date(2026, 9, 2)

    const thisYear = postDate(new Date(2026, 8, 30, 21, 43).toISOString(), now)
    const lastYear = postDate(new Date(2025, 8, 30, 21, 43).toISOString(), now)

    expect(thisYear).toContain('30 сент')
    expect(thisYear).toContain('21:43')
    expect(thisYear).not.toContain('2026')
    expect(lastYear).toContain('2025')
  })
})
