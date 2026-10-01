import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { openSession } from '../session'

const fetchMock = vi.fn<typeof fetch>()

beforeEach(() => {
  vi.stubGlobal('fetch', fetchMock)
})

afterEach(() => {
  fetchMock.mockReset()
  window.history.replaceState(null, '', '/')
})

describe('openSession', () => {
  it('trades the launch token for a session and drops it from the URL', async () => {
    window.history.replaceState(null, '', '/project/7?token=secret&tab=posts')
    fetchMock.mockResolvedValue(new Response(null, { status: 204 }))

    await openSession()

    expect(fetchMock).toHaveBeenCalledOnce()
    const [url, init] = fetchMock.mock.calls[0]!
    expect(url).toBe('/api/session')
    expect(init?.method).toBe('POST')
    expect(init?.body).toBe(JSON.stringify({ token: 'secret' }))
    expect(window.location.pathname + window.location.search).toBe('/project/7?tab=posts')
  })

  it('does nothing without a token', async () => {
    await openSession()

    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('tolerates a spent token', async () => {
    window.history.replaceState(null, '', '/?token=spent')
    fetchMock.mockResolvedValue(new Response(null, { status: 403 }))

    await expect(openSession()).resolves.toBeUndefined()
    expect(window.location.search).toBe('')
  })

  it('reports other failures', async () => {
    window.history.replaceState(null, '', '/?token=secret')
    fetchMock.mockResolvedValue(new Response(null, { status: 500 }))

    await expect(openSession()).rejects.toThrow('500')
  })
})
