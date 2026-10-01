import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it } from 'vitest'

import { fakeBackend, LIBRARY } from '@/__tests__/backend'
import { i18n } from '@/i18n'
import { useLibraryStore } from '@/stores/library'
import WelcomeView from '@/views/WelcomeView.vue'

function mountWelcome() {
  return mount(WelcomeView, { global: { plugins: [i18n] } })
}

function button(wrapper: ReturnType<typeof mountWelcome>, label: string) {
  const found = wrapper.findAll('button').find((candidate) => candidate.text() === label)
  if (!found) {
    throw new Error(`No button labelled "${label}"`)
  }
  return found
}

beforeEach(() => {
  setActivePinia(createPinia())
})

describe('WelcomeView', () => {
  it('creates a library with the first button', async () => {
    const backend = fakeBackend({
      '/api/dialogs/folder': () => Response.json({ path: LIBRARY.path }),
      '/api/library/create': () => Response.json(LIBRARY),
    })
    const wrapper = mountWelcome()

    await button(wrapper, 'Создать библиотеку').trigger('click')
    await flushPromises()

    expect(backend.requests()).toContain('/api/library/create')
    expect(useLibraryStore().current).toEqual(LIBRARY)
  })

  it('opens a library with the second button', async () => {
    const backend = fakeBackend({
      '/api/dialogs/folder': () => Response.json({ path: LIBRARY.path }),
      '/api/library/open': () => Response.json(LIBRARY),
    })
    const wrapper = mountWelcome()

    await button(wrapper, 'Открыть существующую').trigger('click')
    await flushPromises()

    expect(backend.requests()).toContain('/api/library/open')
    expect(useLibraryStore().current).toEqual(LIBRARY)
  })

  it('explains why the chosen folder was refused', async () => {
    fakeBackend({
      '/api/dialogs/folder': () => Response.json({ path: 'D:\\Занято' }),
      '/api/library/create': () => Response.json({ code: 'not_empty' }, { status: 409 }),
    })
    const wrapper = mountWelcome()

    await button(wrapper, 'Создать библиотеку').trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('Папка не пуста')
    expect(wrapper.text()).toContain('D:\\Занято')
  })

  it('explains why the library from the previous run did not open', async () => {
    useLibraryStore().lastFailure = { path: 'E:\\Библиотека', code: 'missing' }

    const wrapper = mountWelcome()

    expect(wrapper.text()).toContain('Не удалось открыть библиотеку')
    expect(wrapper.text()).toContain('Папка не найдена')
    expect(wrapper.text()).toContain('E:\\Библиотека')
  })

  it('falls back to a generic message for a code it does not know', async () => {
    useLibraryStore().actionFailure = { path: 'D:\\Папка', code: 'brand_new_code' }

    const wrapper = mountWelcome()

    expect(wrapper.text()).toContain('Не удалось открыть папку.')
  })
})
