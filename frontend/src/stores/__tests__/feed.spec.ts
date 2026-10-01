import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it } from 'vitest'

import { card, fakeBackend, feedPage, media, post, SETTINGS } from '@/__tests__/backend'
import { type FeedFilters, useFeedStore } from '@/stores/feed'
import { useSettingsStore } from '@/stores/settings'

const FEED = '/api/projects/4242/posts'
const FILTERS: FeedFilters = {
  order: 'desc',
  from: null,
  to: null,
  content: null,
  hideClosed: false,
  hideDeleted: false,
  withText: false,
}

/** Three pages of posts: page N holds the posts N01..N20. */
function pagedBackend(replies: Parameters<typeof fakeBackend>[0] = {}) {
  return fakeBackend({
    [FEED]: (url) => {
      const page = Number(url.searchParams.get('page'))
      const posts = Array.from({ length: page < 3 ? 20 : 5 }, (_, index) =>
        card({ id: page * 100 + index + 1 }),
      )
      return Response.json(feedPage(posts, { total: 45, page }))
    },
    ...replies,
  })
}

function pagesAsked(backend: ReturnType<typeof fakeBackend>): string[] {
  return backend
    .requests()
    .filter((address) => address.startsWith(FEED))
    .map((address) => new URL(address, 'http://x').searchParams.get('page')!)
}

beforeEach(() => {
  setActivePinia(createPinia())
})

describe('feed store', () => {
  it('loads the pages asked for and knows how many there are', async () => {
    const backend = pagedBackend()
    const feed = useFeedStore()

    await feed.show(4242, FILTERS, 1, 2)

    expect(pagesAsked(backend)).toEqual(['1', '2'])
    expect(feed.posts).toHaveLength(40)
    expect([feed.total, feed.pages, feed.firstPage, feed.lastPage]).toEqual([45, 3, 1, 2])
    expect([feed.loading, feed.failed]).toEqual([false, false])
  })

  it('loads only what is not on hand when asked for more', async () => {
    const backend = pagedBackend()
    const feed = useFeedStore()
    await feed.show(4242, FILTERS, 1, 1)

    await feed.show(4242, FILTERS, 1, 1)
    await feed.show(4242, FILTERS, 1, 3)

    expect(pagesAsked(backend)).toEqual(['1', '2', '3'])
    expect(feed.posts).toHaveLength(45)
    expect(feed.posts.at(-1)!.id).toBe(305)
  })

  it('does not ask twice for a page that is already on its way', async () => {
    const backend = pagedBackend()
    const feed = useFeedStore()

    await Promise.all([feed.show(4242, FILTERS, 1, 1), feed.show(4242, { ...FILTERS }, 1, 1)])

    expect(pagesAsked(backend)).toEqual(['1'])
    expect(feed.posts).toHaveLength(20)
  })

  it('starts over when the question changes', async () => {
    const backend = pagedBackend()
    const feed = useFeedStore()
    await feed.show(4242, FILTERS, 1, 2)

    await feed.show(4242, { ...FILTERS, order: 'asc', from: '2026-09-01', to: '2026-09-30' }, 1, 1)

    expect(feed.posts).toHaveLength(20)
    const last = new URL(backend.requests().at(-1)!, 'http://x').searchParams
    expect(last.get('order')).toBe('asc')
    expect(last.get('date_from')).toBe(new Date(2026, 8, 1).toISOString())
    expect(last.get('date_to')).toBe(new Date(2026, 8, 30, 23, 59, 59, 999).toISOString())

    // Another page of the same feed replaces what is on screen.
    await feed.show(4242, { ...FILTERS, order: 'asc', from: '2026-09-01', to: '2026-09-30' }, 3, 3)
    expect(feed.posts).toHaveLength(5)
    expect([feed.firstPage, feed.lastPage]).toEqual([3, 3])
  })

  it('drops the answer to a question that is no longer asked', async () => {
    let release = () => {}
    const slow = new Promise<void>((resolve) => {
      release = resolve
    })
    const backend = pagedBackend({
      '/api/projects/5151/posts': () => Response.json(feedPage([card({ id: 5 })])),
    })
    const feed = useFeedStore()
    const fetchPage = backend.fetchMock.getMockImplementation()!
    backend.fetchMock.mockImplementationOnce(async (input, init) => {
      await slow
      return fetchPage(input, init)
    })

    const first = feed.show(4242, FILTERS, 1, 1)
    await feed.show(5151, FILTERS, 1, 1)
    release()
    await first

    // Only the second project's post is there; the late answer for the first was not added to it.
    expect(feed.posts.map((item) => item.id)).toEqual([5])
  })

  it('remembers a failure and tries again when asked again', async () => {
    const backend = pagedBackend({ [FEED]: () => new Response(null, { status: 500 }) })
    const feed = useFeedStore()

    await feed.show(4242, FILTERS, 1, 1)
    expect([feed.failed, feed.loading, feed.posts.length]).toEqual([true, false, 0])

    backend.serve(FEED, () => Response.json(feedPage([card()])))
    await feed.show(4242, FILTERS, 1, 1)

    expect([feed.failed, feed.posts.length]).toEqual([false, 1])
  })

  it('reloads the pages on screen', async () => {
    const backend = pagedBackend()
    const feed = useFeedStore()
    await feed.show(4242, FILTERS, 2, 3)

    backend.serve(FEED, (url) =>
      Response.json(feedPage([card({ id: Number(url.searchParams.get('page')) })], { total: 41 })),
    )
    await feed.reload()

    expect(feed.posts.map((item) => item.id)).toEqual([2, 3])
    expect(feed.total).toBe(41)
  })

  it('refreshes one post, with its text only where the feed carries texts', async () => {
    const fresh = post({ id: 101, cover: '/media/posts/101/cover', media: [media({ id: 9 })] })
    pagedBackend({ '/api/posts/101': () => Response.json(fresh) })
    const feed = useFeedStore()
    await feed.show(4242, FILTERS, 1, 1)

    await feed.refresh(101)
    // A post that is not on screen is left alone.
    await feed.refresh(999)

    const [first] = feed.posts
    expect(first!.cover).toBe('/media/posts/101/cover')
    expect([first!.html, first!.media]).toEqual([null, []])
    expect(feed.posts).toHaveLength(20)
  })

  it('finds the post a file belongs to', async () => {
    fakeBackend({
      [FEED]: () =>
        Response.json(
          feedPage([
            card({ id: 1, html: '<p>x</p>', media: [media({ id: 7 })] }),
            card({ id: 2, html: '<p>y</p>', media: [media({ id: 8 })] }),
          ]),
        ),
    })
    const feed = useFeedStore()
    await feed.show(4242, { ...FILTERS, withText: true }, 1, 1)

    expect(feed.postOfMedia(8)).toBe(2)
    expect(feed.postOfMedia(99)).toBeNull()
    expect([feed.has(1), feed.has(3)]).toEqual([true, false])
  })
})

describe('settings store', () => {
  it('loads the settings and saves a change', async () => {
    const backend = fakeBackend({
      '/api/settings': (_url, init) =>
        Response.json({ ...SETTINGS, theme: 'dark', ...JSON.parse(String(init?.body ?? '{}')) }),
    })
    const settings = useSettingsStore()

    await settings.load()
    expect(settings.values.theme).toBe('dark')

    await settings.change({ feed_view: 'tile' })

    expect(backend.bodyOf('/api/settings')).toEqual({ feed_view: 'tile' })
    expect(settings.values).toEqual({ theme: 'dark', feed_view: 'tile', hide_closed: false })
  })
})
