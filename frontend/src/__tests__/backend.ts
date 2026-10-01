import { vi } from 'vitest'

import type {
  AccountInfo,
  FeedPage,
  LibraryInfo,
  LibraryStatus,
  MediaInfo,
  PostCard,
  PostDetails,
  ProjectInfo,
  Settings,
  SubscriptionInfo,
  SyncInfo,
} from '@/api/types'

/** Answers a request; gets its address (to read the query) and what was sent with it. */
type Reply = (url: URL, init?: RequestInit) => Response

export const IDLE: SyncInfo = { running: null, queue: [], failures: [], cancelling: false }

export const PROJECT: ProjectInfo = {
  id: 4242,
  url: 'fictional-almanac',
  title: 'Вымышленный альманах',
  intent: 'на выдуманные тексты',
  logo: '/media/projects/4242/logo',
  cover: '/media/projects/4242/cover',
  added_via: 'subscription',
  sync_enabled: true,
  media_mode_audio: 'auto',
  media_mode_video: 'manual',
  media_mode_attach: 'auto',
  video_quality: null,
  last_synced_at: '2026-10-01T18:30:00Z',
  posts: 22,
  posts_without_text: 0,
  posts_deleted: 0,
  posts_closed: 1,
}

export const SETTINGS: Settings = { theme: 'system', feed_view: 'stream', hide_closed: false }

export const SUBSCRIPTION: SubscriptionInfo = {
  id: 4242,
  url: 'fictional-almanac',
  title: 'Вымышленный альманах',
  owner_name: 'Автор Выдуманный',
  level_name: 'Читатель',
  in_library: false,
}

/** A post as the feeds list it; `changes` override the made-up defaults. */
export function card(changes: Partial<PostCard> = {}): PostCard {
  return {
    id: 9001,
    project_id: 4242,
    title: 'Короткая заметка',
    date: '2026-09-30T18:15:00Z',
    excerpt: 'Короткая заметка целиком помещается в список.',
    cover: null,
    closed: false,
    status: 'active',
    text_is_full: true,
    level: { id: 501, name: 'Читатель', price: 300 },
    duration_text: 120,
    duration_audio: 0,
    duration_video: 0,
    has_audio: false,
    has_video: false,
    pinned: false,
    tags: [],
    html: null,
    media: [],
    ...changes,
  }
}

export function media(changes: Partial<MediaInfo> = {}): MediaInfo {
  return {
    id: 1,
    kind: 'image',
    source_id: 'media.sponsr.ru/project/4242/post/9001/image/31/a.webp',
    source_url: 'https://media.sponsr.ru/project/4242/post/9001/image/31/a.webp?1',
    title: null,
    size: null,
    duration: null,
    state: 'pending',
    error: null,
    url: null,
    file_name: null,
    can_open: false,
    ...changes,
  }
}

/** A post as its own page gets it. */
export function post(changes: Partial<PostDetails> = {}): PostDetails {
  return {
    ...card({ html: '<p>Текст поста.</p>' }),
    project: { id: 4242, url: 'fictional-almanac', title: 'Вымышленный альманах' },
    newer: null,
    older: null,
    ...changes,
  }
}

export function feedPage(posts: PostCard[], changes: Partial<FeedPage> = {}): FeedPage {
  return { total: posts.length, page: 1, per_page: 20, posts, ...changes }
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
    '/api/settings': () => Response.json(SETTINGS),
    '/api/library': () => Response.json(NO_LIBRARY),
    '/api/account': () => Response.json(SIGNED_OUT),
    '/api/projects': () => Response.json([]),
    ...replies,
  }

  const fetchMock = vi.fn<typeof fetch>(async (input, init) => {
    const address = String(input)
    // A reply registered for a path answers it with any query.
    const reply = routes[address] ?? routes[address.split('?')[0]!]
    const url = new URL(address, 'http://127.0.0.1')
    return reply ? reply(url, init) : new Response(null, { status: 404 })
  })
  vi.stubGlobal('fetch', fetchMock)

  return {
    fetchMock,
    /** The paths requested so far, in order. */
    requests: () => fetchMock.mock.calls.map(([input]) => String(input)),
    /** The requests so far as `METHOD path`, in order. */
    calls: () =>
      fetchMock.mock.calls.map(([input, init]) => `${init?.method ?? 'GET'} ${String(input)}`),
    /** Answer `path` with `reply` from now on. */
    serve(path: string, reply: Reply): void {
      routes[path] = reply
    },
    /** The JSON body of the latest request to `path` that had one. */
    bodyOf(path: string): unknown {
      const call = fetchMock.mock.calls
        .filter(([input, init]) => String(input) === path && init?.body !== undefined)
        .at(-1)
      return JSON.parse(String(call?.[1]?.body))
    },
  }
}
