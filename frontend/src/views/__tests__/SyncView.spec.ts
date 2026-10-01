import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'

import { fakeBackend, IDLE, PROJECT, SIGNED_IN } from '@/__tests__/backend'
import { buttonIn, withPlugins } from '@/__tests__/mounting'
import type { FailedDownloads, SyncRun } from '@/api/types'
import { useAccountStore } from '@/stores/account'
import { useDownloadsStore } from '@/stores/downloads'
import { useSyncStore } from '@/stores/sync'
import SyncView from '@/views/SyncView.vue'

const NO_FAILURES: FailedDownloads = { total: 0, items: [] }
const RUN: SyncRun = {
  id: 2,
  project_id: 4242,
  title: 'Вымышленный альманах',
  started_at: '2026-10-01T18:30:00Z',
  finished_at: '2026-10-01T18:31:00Z',
  outcome: 'ok',
  full: false,
  posts_new: 3,
  posts_changed: 1,
  posts_deleted: 0,
}

function backend(replies: Parameters<typeof fakeBackend>[0] = {}) {
  return fakeBackend({
    '/api/projects': () =>
      Response.json([PROJECT, { ...PROJECT, id: 5151, title: 'Второй проект' }]),
    '/api/sync/history': () => Response.json([]),
    '/api/downloads/failed': () => Response.json(NO_FAILURES),
    '/api/ffmpeg': () => Response.json({ found: true, path: 'C:\\ffmpeg\\ffmpeg.exe' }),
    ...replies,
  })
}

async function mountSync() {
  const wrapper = mount(SyncView, { ...withPlugins(), attachTo: document.body })
  await flushPromises()
  return wrapper
}

beforeEach(() => {
  setActivePinia(createPinia())
})

afterEach(() => {
  document.body.innerHTML = ''
})

describe('SyncView', () => {
  it('says so when nothing is going on', async () => {
    backend()

    const wrapper = await mountSync()

    expect(wrapper.text()).toContain('Сейчас ничего не обновляется и не скачивается')
    expect(wrapper.text()).not.toContain('Не найден ffmpeg')
    // Signed out: nothing can be updated.
    expect(wrapper.text()).not.toContain('Обновить всё')
  })

  it('shows what is being updated, what waits and what is being downloaded', async () => {
    backend()
    useSyncStore().state = {
      ...IDLE,
      running: { project_id: 4242, title: PROJECT.title, posts_done: 20, posts_total: 40 },
      queue: [5151],
    }
    useDownloadsStore().state = {
      active: [{ key: 'media-1', title: 'Выпуск 12', bytes_done: 0, bytes_total: null }],
      queued: 3,
      done: 1,
      failed: 0,
      cancelling: false,
    }

    const wrapper = await mountSync()

    expect(wrapper.text()).toContain('Обновляется: Вымышленный альманах')
    expect(wrapper.text()).toContain('Ждут обновления')
    expect(wrapper.find('.sync-page__queue').text()).toBe('Второй проект')
    expect(wrapper.text()).toContain('Скачивается медиа')
    expect(wrapper.text()).toContain('Выпуск 12')
    expect(wrapper.text()).not.toContain('Сейчас ничего не обновляется')
  })

  it('starts updating everything', async () => {
    const api = backend({ '/api/sync': () => Response.json(IDLE) })
    useAccountStore().info = SIGNED_IN
    const wrapper = await mountSync()

    buttonIn(wrapper.element, 'Обновить всё').click()
    await flushPromises()

    expect(api.bodyOf('/api/sync')).toEqual({ project_ids: null })
  })

  it('lists the files that failed and tries them again', async () => {
    const failed: FailedDownloads = {
      total: 120,
      items: [
        {
          media_id: 7,
          kind: 'video',
          title: null,
          error: 'no_ffmpeg',
          post_id: 9004,
          post_title: 'Лекция',
          project_id: 4242,
        },
        {
          media_id: 8,
          kind: 'audio',
          title: 'Выпуск 12',
          error: 'brand_new_code',
          post_id: 9003,
          post_title: 'Подкаст',
          project_id: 4242,
        },
      ],
    }
    const api = backend({
      '/api/downloads/failed': () => Response.json(failed),
      '/api/downloads/retry': () => Response.json({ queued: 120 }),
    })
    const wrapper = await mountSync()
    const rows = wrapper.findAll('.sync-page__item').map((row) => row.text())

    expect(wrapper.text()).toContain('Не скачанные файлы: 120')
    expect(rows[0]).toContain('Лекция')
    expect(rows[0]).toContain('видео')
    expect(rows[0]).toContain('Не найден ffmpeg')
    expect(rows[1]).toContain('Выпуск 12')
    expect(rows[1]).toContain('Не удалось скачать')
    expect(wrapper.text()).toContain('И ещё 118.')
    expect(wrapper.find('.sync-page__item a').attributes('href')).toBe('/posts/9004')

    api.serve('/api/downloads/failed', () => Response.json(NO_FAILURES))
    buttonIn(wrapper.element, 'Повторить все').click()
    await flushPromises()

    expect(api.calls()).toContain('POST /api/downloads/retry')
    expect(wrapper.text()).not.toContain('Не скачанные файлы')
  })

  it('shows how the latest updates went', async () => {
    backend({
      '/api/sync/history': () =>
        Response.json([
          RUN,
          { ...RUN, id: 3, outcome: 'failed' },
          { ...RUN, id: 4, outcome: 'cancelled' },
          { ...RUN, id: 5, posts_new: 0, posts_changed: 0 },
          {
            ...RUN,
            id: 6,
            project_id: 777,
            title: null,
            posts_deleted: 2,
            posts_new: 0,
            posts_changed: 0,
          },
        ]),
    })

    const wrapper = await mountSync()
    const rows = wrapper.findAll('.sync-page__item').map((row) => row.text())

    expect(rows[0]).toContain('Вымышленный альманах')
    expect(rows[0]).toContain('Готово')
    expect(rows[0]).toContain('новых: 3, изменённых: 1')
    expect(rows[1]).toContain('Ошибка')
    expect(rows[2]).toContain('Отменено')
    expect(rows[3]).toContain('ничего нового')
    expect(rows[4]).toContain('Проект удалён')
    expect(rows[4]).toContain('удалённых на сайте: 2')
  })

  it('reads the history again when the work stops', async () => {
    const api = backend()
    useSyncStore().state = {
      ...IDLE,
      running: { project_id: 4242, title: PROJECT.title, posts_done: 0, posts_total: null },
    }
    const wrapper = await mountSync()
    expect(wrapper.text()).not.toContain('Последние обновления')

    api.serve('/api/sync/history', () => Response.json([RUN]))
    useSyncStore().handle({ type: 'sync', state: IDLE })
    await flushPromises()

    expect(wrapper.text()).toContain('Последние обновления')
  })

  it('warns that videos cannot be put together without ffmpeg', async () => {
    backend({ '/api/ffmpeg': () => Response.json({ found: false, path: null }) })

    const wrapper = await mountSync()

    expect(wrapper.text()).toContain('Не найден ffmpeg')
    expect(wrapper.text()).toContain('аудио и вложения скачиваются и без него')
  })
})
