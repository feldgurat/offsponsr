import { flushPromises } from '@vue/test-utils'
import { afterEach, describe, expect, it } from 'vitest'

import { createOffsponsrApp } from '@/bootstrap'

import { fakeBackend } from './backend'

afterEach(() => {
  window.history.replaceState(null, '', '/')
})

describe('createOffsponsrApp', () => {
  it('keeps the launch token out of the URL once the router takes over', async () => {
    window.history.replaceState(null, '', '/?token=secret')
    const backend = fakeBackend()

    const app = await createOffsponsrApp()
    const root = document.createElement('div')
    app.mount(root)
    await flushPromises()

    expect(backend.bodyOf('/api/session')).toEqual({ token: 'secret' })
    expect(window.location.search).toBe('')
    expect(root.textContent).toContain('Версия 1.2.3')

    app.unmount()
  })

  it('still starts when the session cannot be opened', async () => {
    window.history.replaceState(null, '', '/?token=secret')
    const backend = fakeBackend()
    backend.fetchMock.mockRejectedValue(new TypeError('network down'))

    const app = await createOffsponsrApp()
    const root = document.createElement('div')
    app.mount(root)
    await flushPromises()

    expect(root.textContent).toContain('Нет связи с приложением')

    app.unmount()
  })
})
