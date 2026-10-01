import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it } from 'vitest'

import { fakeBackend } from '@/__tests__/backend'
import type { DownloadsInfo } from '@/api/types'
import DownloadsPanel from '@/components/DownloadsPanel.vue'
import { i18n } from '@/i18n'
import { useDownloadsStore } from '@/stores/downloads'
import { useSyncStore } from '@/stores/sync'

const plugins = { global: { plugins: [i18n] } }
const IDLE: DownloadsInfo = { active: [], queued: 0, done: 0, failed: 0, cancelling: false }
const BUSY: DownloadsInfo = {
  active: [
    {
      key: 'media-1',
      title: 'Альманах, выпуск 12',
      bytes_done: 12_900_000,
      bytes_total: 95_248_113,
    },
    { key: 'post_cover-2', title: 'Короткая заметка', bytes_done: 0, bytes_total: null },
  ],
  queued: 14,
  done: 5,
  failed: 1,
  cancelling: false,
}

beforeEach(() => {
  setActivePinia(createPinia())
})

describe('downloads store', () => {
  it('starts idle', () => {
    const downloads = useDownloadsStore()

    expect(downloads.state).toEqual(IDLE)
    expect(downloads.busy).toBe(false)
    expect(downloads.total).toBe(0)
  })

  it('counts everything in the batch', () => {
    const downloads = useDownloadsStore()
    downloads.state = BUSY

    expect(downloads.busy).toBe(true)
    expect(downloads.total).toBe(22)
  })

  it('takes its state from the events the sync store listens to', () => {
    useSyncStore().handle({ type: 'downloads', state: BUSY })

    expect(useDownloadsStore().state).toEqual(BUSY)
  })

  it('cancels', async () => {
    const backend = fakeBackend({ '/api/downloads/cancel': () => Response.json(IDLE) })
    const downloads = useDownloadsStore()
    downloads.state = BUSY

    await downloads.cancel()

    expect(backend.requests()).toEqual(['/api/downloads/cancel'])
    expect(downloads.state).toEqual(IDLE)
  })
})

describe('DownloadsPanel', () => {
  it('is not there when nothing is being downloaded', () => {
    expect(mount(DownloadsPanel, plugins).text()).toBe('')
  })

  it('shows how far the batch is and what is in flight', () => {
    useDownloadsStore().state = BUSY

    const text = mount(DownloadsPanel, plugins).text()

    expect(text).toContain('Скачивается медиа')
    expect(text).toContain('6 из 22 файлов')
    expect(text).toContain('27%')
    expect(text).toContain('Альманах, выпуск 12')
    expect(text).toContain('12,3 МБ из 90,8 МБ')
    expect(text).toContain('Короткая заметка')
    expect(text).toContain('Не удалось скачать файлов: 1')
  })

  it('keeps saying what failed after the batch is over', () => {
    useDownloadsStore().state = { ...IDLE, done: 20, failed: 2 }

    const text = mount(DownloadsPanel, plugins).text()

    expect(text).not.toContain('Скачивается медиа')
    expect(text).toContain('Не удалось скачать файлов: 2')
    expect(text).toContain('попробует ещё раз при следующем обновлении')
  })

  it('cancels', async () => {
    const backend = fakeBackend({ '/api/downloads/cancel': () => Response.json(IDLE) })
    useDownloadsStore().state = BUSY
    const wrapper = mount(DownloadsPanel, plugins)

    wrapper.find('button').element.click()
    await flushPromises()

    expect(backend.requests()).toEqual(['/api/downloads/cancel'])
    expect(wrapper.text()).toBe('')
  })

  it('writes sizes the way people read them', () => {
    const sizes: Array<[number, number | null, string]> = [
      [512, 2048, '512 Б из 2 КБ'],
      [1536, 1_048_576, '1,5 КБ из 1 МБ'],
      [5_368_709_120, 10_737_418_240, '5 ГБ из 10 ГБ'],
      [3_000_000, null, '2,9 МБ'],
    ]
    for (const [done, total, expected] of sizes) {
      useDownloadsStore().state = {
        ...IDLE,
        active: [{ key: 'media-1', title: 'Файл', bytes_done: done, bytes_total: total }],
      }

      expect(mount(DownloadsPanel, plugins).text()).toContain(expected)
    }
  })
})
