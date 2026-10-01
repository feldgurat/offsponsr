import { flushPromises } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { createOffsponsrApp } from '@/bootstrap'

const fetchMock = vi.fn<typeof fetch>()

beforeEach(() => {
  vi.stubGlobal('fetch', fetchMock)
})

afterEach(() => {
  fetchMock.mockReset()
  window.history.replaceState(null, '', '/')
})

describe('createOffsponsrApp', () => {
  it('keeps the launch token out of the URL once the router takes over', async () => {
    window.history.replaceState(null, '', '/?token=secret')
    fetchMock.mockImplementation(async (input) =>
      input === '/api/session'
        ? new Response(null, { status: 204 })
        : Response.json({ name: 'offsponsr', version: '1.2.3' }),
    )

    const app = await createOffsponsrApp()
    const root = document.createElement('div')
    app.mount(root)
    await flushPromises()

    expect(window.location.search).toBe('')
    expect(root.textContent).toContain('Версия 1.2.3')

    app.unmount()
  })

  it('still starts when the session cannot be opened', async () => {
    window.history.replaceState(null, '', '/?token=secret')
    fetchMock.mockRejectedValue(new TypeError('network down'))

    const app = await createOffsponsrApp()
    const root = document.createElement('div')
    app.mount(root)
    await flushPromises()

    expect(root.textContent).toContain('Нет связи с приложением')

    app.unmount()
  })
})
