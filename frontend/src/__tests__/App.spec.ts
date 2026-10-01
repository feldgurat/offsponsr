import { flushPromises, mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { describe, expect, it } from 'vitest'

import App from '@/App.vue'
import { i18n } from '@/i18n'
import { createAppRouter } from '@/router'
import { useDownloadsStore } from '@/stores/downloads'
import { useSyncStore } from '@/stores/sync'
import { useThemeStore } from '@/stores/theme'

import { fakeBackend, LIBRARY } from './backend'

async function mountApp() {
  const router = createAppRouter()
  await router.push('/')
  await router.isReady()
  const pinia = createPinia()
  const wrapper = mount(App, { global: { plugins: [pinia, router, i18n] } })
  await flushPromises()
  return Object.assign(wrapper, { pinia, router })
}

describe('App', () => {
  it('offers to create or open a library when there is none', async () => {
    fakeBackend()

    const wrapper = await mountApp()

    expect(wrapper.text()).toContain('Создать библиотеку')
    expect(wrapper.text()).toContain('Открыть существующую')
    expect(wrapper.text()).toContain('Версия 1.2.3')
    expect(wrapper.text()).not.toContain('В библиотеке пока нет проектов')
  })

  it('shows the library when one is open', async () => {
    fakeBackend({
      '/api/library': () => Response.json({ library: LIBRARY, last_failure: null }),
    })

    const wrapper = await mountApp()

    expect(wrapper.text()).toContain('Библиотека')
    expect(wrapper.text()).toContain('В библиотеке пока нет проектов')
    expect(wrapper.text()).not.toContain('Создать библиотеку')
  })

  it('leads to the sync page and the settings from any page', async () => {
    fakeBackend({
      '/api/library': () => Response.json({ library: LIBRARY, last_failure: null }),
      '/api/sync/history': () => Response.json([]),
      '/api/downloads/failed': () => Response.json({ total: 0, items: [] }),
      '/api/ffmpeg': () => Response.json({ found: true, path: 'ffmpeg' }),
    })
    const wrapper = await mountApp()
    const links = wrapper.findAll('.app__nav a')

    expect(links.map((link) => link.text())).toEqual(['Библиотека', 'Синхронизация', 'Настройки'])

    await links[1]!.trigger('click')
    await flushPromises()
    expect(wrapper.router.currentRoute.value.name).toBe('sync')
    expect(wrapper.find('h1').text()).toBe('Синхронизация')

    await links[2]!.trigger('click')
    await flushPromises()
    expect(wrapper.find('h1').text()).toBe('Настройки')
  })

  it('tells in the header what is going on in the background', async () => {
    fakeBackend({
      '/api/library': () => Response.json({ library: LIBRARY, last_failure: null }),
    })
    const wrapper = await mountApp()
    const sync = useSyncStore(wrapper.pinia)
    const downloads = useDownloadsStore(wrapper.pinia)
    const idle = { running: null, queue: [], failures: [], cancelling: false }

    sync.state = {
      ...idle,
      running: { project_id: 1, title: 'Альманах', posts_done: 0, posts_total: null },
    }
    await flushPromises()
    expect(wrapper.find('.activity').text()).toBe('Обновляется: Альманах')

    sync.state = idle
    downloads.state = {
      active: [{ key: 'media-1', title: 'Файл', bytes_done: 0, bytes_total: null }],
      queued: 20,
      done: 3,
      failed: 0,
      cancelling: false,
    }
    await flushPromises()
    expect(wrapper.find('.activity').text()).toBe('Скачивается 21 файл')

    // What failed stays as a number on the icon once the work is over.
    downloads.state = { active: [], queued: 0, done: 22, failed: 2, cancelling: false }
    await flushPromises()
    expect(wrapper.find('.activity').text()).toContain('Синхронизация')
    expect(wrapper.find('.activity .ant-badge').text()).toContain('2')
  })

  it('applies the saved theme', async () => {
    fakeBackend({
      '/api/settings': () => Response.json({ theme: 'dark', feed_view: 'list', hide_closed: true }),
    })

    const wrapper = await mountApp()

    expect(useThemeStore(wrapper.pinia).isDark).toBe(true)
    expect(document.documentElement.style.getPropertyValue('color-scheme')).toBe('dark')
  })

  it('reports a lost backend', async () => {
    fakeBackend({ '/api/app': () => new Response(null, { status: 401 }) })

    const wrapper = await mountApp()

    expect(wrapper.text()).toContain('Нет связи с приложением')
    expect(wrapper.text()).not.toContain('Создать библиотеку')
  })
})
