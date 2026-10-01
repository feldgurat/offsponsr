import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'

import { fakeBackend, LIBRARY, PROJECT, SETTINGS, SIGNED_IN, SIGNED_OUT } from '@/__tests__/backend'
import { buttonIn, withPlugins } from '@/__tests__/mounting'
import { useAccountStore } from '@/stores/account'
import { useLibraryStore } from '@/stores/library'
import { useProjectsStore } from '@/stores/projects'
import { useSettingsStore } from '@/stores/settings'
import { useSyncStore } from '@/stores/sync'
import { useThemeStore } from '@/stores/theme'
import SettingsView from '@/views/SettingsView.vue'

function backend(replies: Parameters<typeof fakeBackend>[0] = {}) {
  return fakeBackend({
    '/api/projects': () => Response.json([PROJECT]),
    '/api/ffmpeg': () => Response.json({ found: true, path: 'C:\\ffmpeg\\ffmpeg.exe' }),
    '/api/settings': (_url, init) =>
      Response.json({ ...SETTINGS, ...JSON.parse(String(init?.body ?? '{}')) }),
    ...replies,
  })
}

async function mountSettings() {
  useLibraryStore().current = LIBRARY
  const wrapper = mount(SettingsView, { ...withPlugins(), attachTo: document.body })
  await flushPromises()
  return wrapper
}

beforeEach(() => {
  setActivePinia(createPinia())
})

afterEach(() => {
  document.body.innerHTML = ''
})

describe('SettingsView', () => {
  it('changes the theme at once and saves it', async () => {
    const api = backend()
    const wrapper = await mountSettings()

    await wrapper.find('input[value="dark"]').setValue(true)
    await flushPromises()

    expect(useThemeStore().isDark).toBe(true)
    expect(api.bodyOf('/api/settings')).toEqual({ theme: 'dark' })
    expect(api.calls()).toContain('PATCH /api/settings')
  })

  it('keeps the chosen theme for this run even if it could not be saved', async () => {
    backend({ '/api/settings': () => new Response(null, { status: 500 }) })
    const wrapper = await mountSettings()

    await wrapper.find('input[value="dark"]').setValue(true)
    await flushPromises()

    expect(useSettingsStore().values.theme).toBe('dark')
  })

  it('shows who is signed in and signs out', async () => {
    const api = backend({ '/api/account/logout': () => Response.json(SIGNED_OUT) })
    useAccountStore().info = SIGNED_IN
    const wrapper = await mountSettings()

    expect(wrapper.text()).toContain('Вы вошли как reader@example.com')

    buttonIn(wrapper.element, 'Выйти').click()
    await flushPromises()

    expect(api.calls()).toContain('POST /api/account/logout')
    expect(wrapper.text()).toContain('Вход не выполнен')
    expect(buttonIn(wrapper.element, 'Войти')).toBeTruthy()
  })

  it('shows where the library is and opens another one', async () => {
    const other = { id: 'other-id', path: 'E:\\Другая' }
    const api = backend({
      '/api/dialogs/folder': () => Response.json({ path: other.path }),
      '/api/library/open': () => Response.json(other),
      '/api/account': () => Response.json(SIGNED_OUT),
    })
    const wrapper = await mountSettings()
    expect(wrapper.text()).toContain('D:\\Библиотека')

    api.serve('/api/projects', () => Response.json([]))
    buttonIn(wrapper.element, 'Открыть другую').click()
    await flushPromises()

    expect(api.bodyOf('/api/library/open')).toEqual({ path: other.path })
    expect(wrapper.text()).toContain('E:\\Другая')
    // The projects on hand were the other library's.
    expect(useProjectsStore().list).toEqual([])
  })

  it('explains why the library could not be switched', async () => {
    backend({
      '/api/dialogs/folder': () => Response.json({ path: 'E:\\Занята' }),
      '/api/library/create': () => Response.json({ code: 'not_empty' }, { status: 409 }),
      '/api/library/open': () => Response.json({ code: 'sync_running' }, { status: 409 }),
    })
    const wrapper = await mountSettings()

    buttonIn(wrapper.element, 'Создать новую').click()
    await flushPromises()
    expect(wrapper.text()).toContain('Папка не пуста')

    buttonIn(wrapper.element, 'Открыть другую').click()
    await flushPromises()
    expect(wrapper.text()).toContain('Дождитесь конца обновления и загрузок')
  })

  it('does not let the library be switched while it is being written to', async () => {
    backend()
    useSyncStore().state = {
      running: { project_id: 4242, title: PROJECT.title, posts_done: 0, posts_total: null },
      queue: [],
      failures: [],
      cancelling: false,
    }

    const wrapper = await mountSettings()

    expect(buttonIn(wrapper.element, 'Открыть другую').disabled).toBe(true)
    expect(buttonIn(wrapper.element, 'Создать новую').disabled).toBe(true)
  })

  it('tells whether there is an ffmpeg', async () => {
    backend()
    const found = await mountSettings()
    expect(found.text()).toContain('C:\\ffmpeg\\ffmpeg.exe')
    found.unmount()

    backend({ '/api/ffmpeg': () => Response.json({ found: false, path: null }) })
    const missing = await mountSettings()
    expect(missing.text()).toContain('Не найден ffmpeg')
  })

  it('has the settings of every project', async () => {
    const api = backend({
      '/api/projects/4242': () =>
        Response.json({
          project: { ...PROJECT, sync_enabled: false },
          to_download: { files: 0, bytes: 0, files_without_size: 0 },
        }),
    })
    const wrapper = await mountSettings()

    await wrapper.find('.ant-collapse-header').trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('Обновлять по кнопке «Обновить всё»')
    expect(wrapper.text()).toContain('Качество видео')

    await wrapper.find('button[role="switch"]').trigger('click')
    await flushPromises()

    expect(api.bodyOf('/api/projects/4242')).toEqual({ sync_enabled: false })
    expect(useProjectsStore().byId(4242)!.sync_enabled).toBe(false)
  })
})
