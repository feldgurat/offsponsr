import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'

import {
  fakeBackend,
  ffmpeg,
  LIBRARY,
  NO_FFMPEG,
  PROJECT,
  SETTINGS,
  SIGNED_IN,
  SIGNED_OUT,
} from '@/__tests__/backend'
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
    '/api/ffmpeg': () => Response.json(ffmpeg()),
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

  describe('ffmpeg', () => {
    it('tells which ffmpeg the videos are put together with', async () => {
      backend()

      const wrapper = await mountSettings()

      expect(wrapper.text()).toContain('Найден, видео будет собираться им:')
      expect(wrapper.text()).toContain('C:\\ffmpeg\\bin\\ffmpeg.exe')
      expect(wrapper.text()).toContain('Версия 9.0.2-essentials_build')
      expect(wrapper.text()).not.toContain('Установить ffmpeg')
      expect(wrapper.text()).not.toContain('Проверить снова')
    })

    it('installs ffmpeg with winget after a yes', async () => {
      const api = backend({
        '/api/ffmpeg': () => Response.json(NO_FFMPEG),
        '/api/ffmpeg/install': () => Response.json({ ...NO_FFMPEG, installing: true }),
      })
      const wrapper = await mountSettings()
      expect(wrapper.text()).toContain('Не найден ffmpeg')
      expect(wrapper.text()).toContain('offsponsr может установить ffmpeg сам')

      buttonIn(wrapper.element, 'Установить ffmpeg').click()
      await flushPromises()

      // Nothing is installed before the user has read what will be done and agreed.
      expect(document.body.textContent).toContain('winget install Gyan.FFmpeg.Essentials')
      expect(document.body.textContent).toContain('около 110 МБ')
      expect(api.calls()).not.toContain('POST /api/ffmpeg/install')

      buttonIn(document.body, 'Установить').click()
      await flushPromises()

      expect(api.calls()).toContain('POST /api/ffmpeg/install')
      expect(wrapper.text()).toContain('ffmpeg устанавливается…')
      expect(buttonIn(wrapper.element, 'Проверить снова').disabled).toBe(true)

      // winget is through: the backend tells, the page shows the ffmpeg.
      useSyncStore().handle({ type: 'ffmpeg', state: ffmpeg() })
      await flushPromises()

      expect(wrapper.text()).toContain('C:\\ffmpeg\\bin\\ffmpeg.exe')
      expect(wrapper.text()).not.toContain('ffmpeg устанавливается…')
    })

    it('tells why the installation failed', async () => {
      backend({ '/api/ffmpeg': () => Response.json({ ...NO_FFMPEG, error: 'install_failed' }) })

      const wrapper = await mountSettings()

      expect(wrapper.text()).toContain('winget не смог установить ffmpeg')
    })

    it('explains what to do on a Windows without winget', async () => {
      const api = backend({
        '/api/ffmpeg': () => Response.json({ ...NO_FFMPEG, can_install: false }),
        '/api/open-link': () => new Response(null, { status: 204 }),
      })
      const wrapper = await mountSettings()

      expect(wrapper.text()).toContain('На этом компьютере нет winget')
      expect(wrapper.text()).not.toContain('Установить ffmpeg')

      buttonIn(wrapper.element, 'Открыть gyan.dev').click()
      await flushPromises()

      expect(api.bodyOf('/api/open-link')).toEqual({ url: 'https://www.gyan.dev/ffmpeg/builds/' })
    })

    it('names the way to install ffmpeg on the other systems', async () => {
      backend({
        '/api/ffmpeg': () => Response.json({ ...NO_FFMPEG, can_install: false, platform: 'macos' }),
      })
      const mac = await mountSettings()
      expect(mac.text()).toContain('brew install ffmpeg')
      expect(mac.text()).not.toContain('gyan.dev')
      mac.unmount()

      backend({
        '/api/ffmpeg': () => Response.json({ ...NO_FFMPEG, can_install: false, platform: 'linux' }),
      })
      const linux = await mountSettings()
      expect(linux.text()).toContain('sudo apt install ffmpeg')
    })

    it('looks for ffmpeg again when asked', async () => {
      const api = backend({
        '/api/ffmpeg': () => Response.json({ ...NO_FFMPEG, can_install: false }),
        '/api/ffmpeg/check': () => Response.json(ffmpeg({ can_install: false })),
      })
      const wrapper = await mountSettings()

      buttonIn(wrapper.element, 'Проверить снова').click()
      await flushPromises()

      expect(api.calls()).toContain('POST /api/ffmpeg/check')
      expect(wrapper.text()).toContain('Найден, видео будет собираться им:')
    })

    it('lets the user point at their ffmpeg and take that back', async () => {
      const mine = ffmpeg({ path: 'D:\\tools\\ffmpeg.exe', chosen: true })
      const api = backend({
        '/api/ffmpeg/choose': () => Response.json(mine),
        '/api/ffmpeg/choice': () => Response.json(ffmpeg()),
      })
      const wrapper = await mountSettings()
      expect(wrapper.text()).not.toContain('Забыть указанный файл')

      buttonIn(wrapper.element, 'Указать файл ffmpeg…').click()
      await flushPromises()

      // The file is picked in the system's dialog; the page sends no path.
      expect(api.calls()).toContain('POST /api/ffmpeg/choose')
      expect(wrapper.text()).toContain('Указан вами, видео будет собираться им:')
      expect(wrapper.text()).toContain('D:\\tools\\ffmpeg.exe')

      buttonIn(wrapper.element, 'Забыть указанный файл').click()
      await flushPromises()

      expect(api.calls()).toContain('DELETE /api/ffmpeg/choice')
      expect(wrapper.text()).toContain('C:\\ffmpeg\\bin\\ffmpeg.exe')
    })

    it('says so when the file pointed at is not an ffmpeg', async () => {
      backend({
        '/api/ffmpeg/choose': () => Response.json({ code: 'not_ffmpeg' }, { status: 422 }),
      })
      const wrapper = await mountSettings()

      buttonIn(wrapper.element, 'Указать файл ffmpeg…').click()
      await flushPromises()

      expect(wrapper.text()).toContain('Этот файл не похож на ffmpeg')
      // What was there stays.
      expect(wrapper.text()).toContain('C:\\ffmpeg\\bin\\ffmpeg.exe')
    })
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
