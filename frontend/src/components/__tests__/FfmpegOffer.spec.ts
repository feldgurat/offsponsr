import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'

import { fakeBackend, ffmpeg, NO_FFMPEG } from '@/__tests__/backend'
import { buttonIn, withPlugins } from '@/__tests__/mounting'
import FfmpegOffer from '@/components/FfmpegOffer.vue'
import { useFfmpegStore } from '@/stores/ffmpeg'

async function mountOffer() {
  const wrapper = mount(FfmpegOffer, { ...withPlugins(), attachTo: document.body })
  await flushPromises()
  return wrapper
}

beforeEach(() => {
  setActivePinia(createPinia())
})

afterEach(() => {
  document.body.innerHTML = ''
})

describe('FfmpegOffer', () => {
  it('shows nothing while there is an ffmpeg, or before the backend has told', async () => {
    fakeBackend({ '/api/ffmpeg': () => Response.json(ffmpeg()) })
    const found = await mountOffer()
    expect(found.text()).toBe('')
    found.unmount()

    setActivePinia(createPinia())
    fakeBackend()
    const unknown = await mountOffer()
    expect(unknown.text()).toBe('')
  })

  it('asks the backend once, however many of them are on the page', async () => {
    const backend = fakeBackend({ '/api/ffmpeg': () => Response.json(NO_FFMPEG) })

    await mountOffer()
    await mountOffer()

    expect(backend.calls()).toEqual(['GET /api/ffmpeg'])
  })

  it('installs ffmpeg only after the user has agreed', async () => {
    const backend = fakeBackend({
      '/api/ffmpeg': () => Response.json(NO_FFMPEG),
      '/api/ffmpeg/install': () => Response.json({ ...NO_FFMPEG, installing: true }),
    })
    const wrapper = await mountOffer()

    buttonIn(wrapper.element, 'Установить ffmpeg').click()
    await flushPromises()
    expect(document.body.textContent).toContain('Установить ffmpeg?')

    buttonIn(document.body, 'Не сейчас').click()
    await flushPromises()
    expect(backend.calls()).not.toContain('POST /api/ffmpeg/install')

    buttonIn(wrapper.element, 'Установить ffmpeg').click()
    await flushPromises()
    buttonIn(document.body, 'Установить').click()
    await flushPromises()

    expect(backend.calls()).toContain('POST /api/ffmpeg/install')
    expect(wrapper.text()).toBe('ffmpeg устанавливается…')
    expect(wrapper.find('button').exists()).toBe(false)
  })

  it('keeps the refusal of the backend for the page to show', async () => {
    fakeBackend({
      '/api/ffmpeg': () => Response.json(NO_FFMPEG),
      '/api/ffmpeg/install': () => Response.json({ code: 'no_winget' }, { status: 409 }),
    })
    const wrapper = await mountOffer()

    buttonIn(wrapper.element, 'Установить ffmpeg').click()
    await flushPromises()
    buttonIn(document.body, 'Установить').click()
    await flushPromises()

    expect(useFfmpegStore().failure).toBe('no_winget')
    expect(buttonIn(wrapper.element, 'Установить ffmpeg')).toBeTruthy()
  })

  it('leads to the settings where the app cannot install ffmpeg itself', async () => {
    fakeBackend({ '/api/ffmpeg': () => Response.json({ ...NO_FFMPEG, can_install: false }) })

    const wrapper = await mountOffer()

    expect(wrapper.find('button').exists()).toBe(false)
    expect(wrapper.find('a').text()).toBe('Как установить ffmpeg')
    expect(wrapper.find('a').attributes('href')).toBe('/settings')
  })
})
