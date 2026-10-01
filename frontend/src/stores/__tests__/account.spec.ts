import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it } from 'vitest'

import { fakeBackend, SIGNED_IN, SIGNED_OUT } from '@/__tests__/backend'
import { useAccountStore } from '@/stores/account'

beforeEach(() => {
  setActivePinia(createPinia())
})

describe('account store', () => {
  it('starts signed out and loads the real state', async () => {
    fakeBackend({ '/api/account': () => Response.json(SIGNED_IN) })
    const account = useAccountStore()

    expect(account.info).toEqual(SIGNED_OUT)

    await account.load()

    expect(account.info).toEqual(SIGNED_IN)
  })

  it('signs in through the login window', async () => {
    const backend = fakeBackend({ '/api/account/login': () => Response.json(SIGNED_IN) })
    const account = useAccountStore()

    const done = account.login()
    expect(account.busy).toBe(true)

    expect(await done).toBe(true)
    expect(backend.requests()).toEqual(['/api/account/login'])
    expect(account.info).toEqual(SIGNED_IN)
    expect(account.busy).toBe(false)
    expect(account.failure).toBeNull()
  })

  it('stays signed out when the login window is closed', async () => {
    fakeBackend({ '/api/account/login': () => Response.json(SIGNED_OUT) })
    const account = useAccountStore()

    expect(await account.login()).toBe(true)
    expect(account.info).toEqual(SIGNED_OUT)
    expect(account.failure).toBeNull()
  })

  it('signs in with a cookie header', async () => {
    const backend = fakeBackend({ '/api/account/login/cookie': () => Response.json(SIGNED_IN) })
    const account = useAccountStore()

    expect(await account.loginWithCookie('sid=good')).toBe(true)
    expect(backend.bodyOf('/api/account/login/cookie')).toEqual({ cookie: 'sid=good' })
    expect(account.info).toEqual(SIGNED_IN)
  })

  it('keeps the reason of a failed sign-in until it is dismissed', async () => {
    fakeBackend({
      '/api/account/login/cookie': () => Response.json({ code: 'invalid_cookie' }, { status: 422 }),
    })
    const account = useAccountStore()

    expect(await account.loginWithCookie('sid=stale')).toBe(false)
    expect(account.failure).toBe('invalid_cookie')
    expect(account.info).toEqual(SIGNED_OUT)
    expect(account.busy).toBe(false)

    account.dismissFailure()

    expect(account.failure).toBeNull()
  })

  it('reports an unexpected failure as unknown', async () => {
    const backend = fakeBackend()
    backend.fetchMock.mockRejectedValue(new TypeError('network down'))
    const account = useAccountStore()

    expect(await account.login()).toBe(false)
    expect(account.failure).toBe('unknown')
  })

  it('signs out', async () => {
    const backend = fakeBackend({ '/api/account/logout': () => Response.json(SIGNED_OUT) })
    const account = useAccountStore()
    account.info = SIGNED_IN

    await account.logout()

    expect(backend.requests()).toEqual(['/api/account/logout'])
    expect(account.info).toEqual(SIGNED_OUT)
  })
})
