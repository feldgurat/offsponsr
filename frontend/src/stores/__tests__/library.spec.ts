import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it } from 'vitest'

import { fakeBackend, LIBRARY, SIGNED_IN } from '@/__tests__/backend'
import { useAccountStore } from '@/stores/account'
import { useLibraryStore } from '@/stores/library'

const chosen = (path: string | null) => () => Response.json({ path })

beforeEach(() => {
  setActivePinia(createPinia())
})

describe('library store', () => {
  it('loads the open library and the failure of the previous one', async () => {
    const failure = { path: 'E:\\Старая', code: 'missing' }
    fakeBackend({
      '/api/library': () => Response.json({ library: null, last_failure: failure }),
    })
    const library = useLibraryStore()

    await library.load()

    expect(library.current).toBeNull()
    expect(library.lastFailure).toEqual(failure)
  })

  it('creates a library in the folder the user picked', async () => {
    const backend = fakeBackend({
      '/api/dialogs/folder': chosen(LIBRARY.path),
      '/api/library/create': () => Response.json(LIBRARY),
    })
    const library = useLibraryStore()
    library.lastFailure = { path: 'E:\\Старая', code: 'missing' }

    await library.create()

    expect(backend.requests()).toEqual([
      '/api/dialogs/folder',
      '/api/library/create',
      '/api/account',
    ])
    expect(backend.bodyOf('/api/library/create')).toEqual({ path: LIBRARY.path })
    expect(library.current).toEqual(LIBRARY)
    expect(library.lastFailure).toBeNull()
    expect(library.actionFailure).toBeNull()
    expect(library.busy).toBe(false)
  })

  it('opens an existing library', async () => {
    const backend = fakeBackend({
      '/api/dialogs/folder': chosen(LIBRARY.path),
      '/api/library/open': () => Response.json(LIBRARY),
    })
    const library = useLibraryStore()

    await library.open()

    expect(backend.requests()).toEqual(['/api/dialogs/folder', '/api/library/open', '/api/account'])
    expect(library.current).toEqual(LIBRARY)
  })

  it('finds out who is signed in to the library it opened', async () => {
    fakeBackend({
      '/api/dialogs/folder': chosen(LIBRARY.path),
      '/api/library/open': () => Response.json(LIBRARY),
      '/api/account': () => Response.json(SIGNED_IN),
    })

    await useLibraryStore().open()

    expect(useAccountStore().info).toEqual(SIGNED_IN)
  })

  it('opens the library even if the account cannot be read', async () => {
    fakeBackend({
      '/api/dialogs/folder': chosen(LIBRARY.path),
      '/api/library/open': () => Response.json(LIBRARY),
      '/api/account': () => new Response(null, { status: 500 }),
    })
    const library = useLibraryStore()

    await library.open()

    expect(library.current).toEqual(LIBRARY)
    expect(library.actionFailure).toBeNull()
  })

  it('does nothing when the folder dialog is cancelled', async () => {
    const backend = fakeBackend({ '/api/dialogs/folder': chosen(null) })
    const library = useLibraryStore()

    await library.create()

    expect(backend.requests()).toEqual(['/api/dialogs/folder'])
    expect(library.current).toBeNull()
    expect(library.actionFailure).toBeNull()
    expect(library.busy).toBe(false)
  })

  it('keeps the reason when the backend refuses the folder', async () => {
    fakeBackend({
      '/api/dialogs/folder': chosen('D:\\Занято'),
      '/api/library/create': () =>
        Response.json({ code: 'not_empty', path: 'D:\\Занято' }, { status: 409 }),
    })
    const library = useLibraryStore()

    await library.create()

    expect(library.current).toBeNull()
    expect(library.actionFailure).toEqual({ path: 'D:\\Занято', code: 'not_empty' })
    expect(library.busy).toBe(false)
  })

  it('reports an unexpected failure as unknown', async () => {
    fakeBackend({
      '/api/dialogs/folder': chosen('D:\\Папка'),
      '/api/library/open': () => new Response('boom', { status: 500 }),
    })
    const library = useLibraryStore()

    await library.open()

    expect(library.actionFailure).toEqual({ path: 'D:\\Папка', code: 'unknown' })
  })
})
