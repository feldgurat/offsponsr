import { vi } from 'vitest'

import type {
  AccountInfo,
  LibraryInfo,
  LibraryStatus,
  ProjectInfo,
  SubscriptionInfo,
  SyncInfo,
} from '@/api/types'

type Reply = () => Response

export const IDLE: SyncInfo = { running: null, queue: [], failures: [], cancelling: false }

export const PROJECT: ProjectInfo = {
  id: 4242,
  url: 'fictional-almanac',
  title: 'Вымышленный альманах',
  added_via: 'subscription',
  sync_enabled: true,
  last_synced_at: '2026-10-01T18:30:00Z',
  posts: 22,
  posts_without_text: 0,
  posts_deleted: 0,
}

export const SUBSCRIPTION: SubscriptionInfo = {
  id: 4242,
  url: 'fictional-almanac',
  title: 'Вымышленный альманах',
  owner_name: 'Автор Выдуманный',
  level_name: 'Читатель',
  in_library: false,
}

export const LIBRARY: LibraryInfo = { id: 'library-id', path: 'D:\\Библиотека' }

export const NO_LIBRARY: LibraryStatus = { library: null, last_failure: null }

export const SIGNED_OUT: AccountInfo = { signed_in: false, email: null, expired: false }

export const SIGNED_IN: AccountInfo = {
  signed_in: true,
  email: 'reader@example.com',
  expired: false,
}

/**
 * A fake backend: stubs `fetch` and answers each API path with the reply registered for it.
 * A path nobody registered answers 404, like the real one.
 */
export function fakeBackend(replies: Record<string, Reply> = {}) {
  const routes: Record<string, Reply> = {
    '/api/session': () => new Response(null, { status: 204 }),
    '/api/app': () => Response.json({ name: 'offsponsr', version: '1.2.3' }),
    '/api/library': () => Response.json(NO_LIBRARY),
    '/api/account': () => Response.json(SIGNED_OUT),
    '/api/projects': () => Response.json([]),
    ...replies,
  }

  const fetchMock = vi.fn<typeof fetch>(async (input) => {
    const reply = routes[String(input)]
    return reply ? reply() : new Response(null, { status: 404 })
  })
  vi.stubGlobal('fetch', fetchMock)

  return {
    fetchMock,
    /** The paths requested so far, in order. */
    requests: () => fetchMock.mock.calls.map(([input]) => String(input)),
    /** The JSON body of the latest request to `path` that had one. */
    bodyOf(path: string): unknown {
      const call = fetchMock.mock.calls
        .filter(([input, init]) => String(input) === path && init?.body !== undefined)
        .at(-1)
      return JSON.parse(String(call?.[1]?.body))
    },
  }
}
