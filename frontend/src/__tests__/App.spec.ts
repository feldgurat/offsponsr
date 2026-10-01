import { flushPromises, mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import App from '@/App.vue'
import { i18n } from '@/i18n'
import { createAppRouter } from '@/router'

const fetchMock = vi.fn<typeof fetch>()

async function mountApp() {
  const router = createAppRouter()
  await router.push('/')
  await router.isReady()
  const wrapper = mount(App, { global: { plugins: [createPinia(), router, i18n] } })
  await flushPromises()
  return wrapper
}

beforeEach(() => {
  vi.stubGlobal('fetch', fetchMock)
})

afterEach(() => {
  fetchMock.mockReset()
})

describe('App', () => {
  it('shows the library and the version once the backend answers', async () => {
    fetchMock.mockResolvedValue(Response.json({ name: 'offsponsr', version: '1.2.3' }))

    const wrapper = await mountApp()

    expect(fetchMock).toHaveBeenCalledWith('/api/app', undefined)
    expect(wrapper.text()).toContain('Библиотека')
    expect(wrapper.text()).toContain('В библиотеке пока нет проектов')
    expect(wrapper.text()).toContain('Версия 1.2.3')
  })

  it('reports a lost backend', async () => {
    fetchMock.mockResolvedValue(new Response(null, { status: 401 }))

    const wrapper = await mountApp()

    expect(wrapper.text()).toContain('Нет связи с приложением')
    expect(wrapper.text()).not.toContain('Библиотека')
  })
})
