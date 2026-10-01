import { flushPromises, mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { describe, expect, it } from 'vitest'

import App from '@/App.vue'
import { i18n } from '@/i18n'
import { createAppRouter } from '@/router'

import { fakeBackend, LIBRARY } from './backend'

async function mountApp() {
  const router = createAppRouter()
  await router.push('/')
  await router.isReady()
  const wrapper = mount(App, { global: { plugins: [createPinia(), router, i18n] } })
  await flushPromises()
  return wrapper
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

  it('reports a lost backend', async () => {
    fakeBackend({ '/api/app': () => new Response(null, { status: 401 }) })

    const wrapper = await mountApp()

    expect(wrapper.text()).toContain('Нет связи с приложением')
    expect(wrapper.text()).not.toContain('Создать библиотеку')
  })
})
