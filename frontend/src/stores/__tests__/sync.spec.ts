import { flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { fakeBackend, IDLE, PROJECT, SIGNED_OUT } from '@/__tests__/backend'
import type { SyncInfo } from '@/api/types'
import { russianPlural } from '@/i18n'
import { useAccountStore } from '@/stores/account'
import { useProjectsStore } from '@/stores/projects'
import { useSyncStore } from '@/stores/sync'

const RUNNING: SyncInfo = {
  running: { project_id: 4242, title: 'Вымышленный альманах', posts_done: 20, posts_total: 45 },
  queue: [5151],
  failures: [],
  cancelling: false,
}

/** Stands in for the browser's EventSource, which jsdom doesn't have. */
class FakeEventSource {
  static opened: FakeEventSource[] = []
  onmessage: ((message: MessageEvent<string>) => void) | null = null
  closed = false

  constructor(readonly url: string) {
    FakeEventSource.opened.push(this)
  }

  push(event: unknown): void {
    this.onmessage?.(new MessageEvent('message', { data: JSON.stringify(event) }))
  }

  close(): void {
    this.closed = true
  }
}

beforeEach(() => {
  setActivePinia(createPinia())
  FakeEventSource.opened = []
  vi.stubGlobal('EventSource', FakeEventSource)
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('projects store', () => {
  it('loads the projects of the library', async () => {
    fakeBackend({ '/api/projects': () => Response.json([PROJECT]) })
    const projects = useProjectsStore()

    expect(projects.loaded).toBe(false)
    await projects.load()

    expect(projects.list).toEqual([PROJECT])
    expect(projects.loaded).toBe(true)
  })

  it('adds projects and reloads the list', async () => {
    const backend = fakeBackend({ '/api/projects': () => Response.json([PROJECT]) })
    const projects = useProjectsStore()

    await projects.add([4242], '  https://sponsr.ru/second/  ')

    expect(backend.bodyOf('/api/projects')).toEqual({
      subscription_ids: [4242],
      address: 'https://sponsr.ru/second/',
    })
    expect(projects.list).toEqual([PROJECT])
  })

  it('sends no address when the field is empty', async () => {
    const backend = fakeBackend()

    await useProjectsStore().add([4242], '   ')

    expect(backend.bodyOf('/api/projects')).toEqual({ subscription_ids: [4242], address: null })
  })

  it('passes on the reason when adding fails', async () => {
    fakeBackend({
      '/api/projects': () => Response.json({ code: 'invalid_address' }, { status: 422 }),
    })

    await expect(useProjectsStore().add([], 'nonsense here')).rejects.toMatchObject({
      code: 'invalid_address',
    })
  })
})

describe('sync store', () => {
  it('starts idle', () => {
    const sync = useSyncStore()

    expect(sync.state).toEqual(IDLE)
    expect(sync.busy).toBe(false)
    expect(sync.statusOf(4242)).toBe('idle')
  })

  it('updates all projects or the chosen ones', async () => {
    const backend = fakeBackend({ '/api/sync': () => Response.json(RUNNING) })
    const sync = useSyncStore()

    await sync.start()
    expect(backend.bodyOf('/api/sync')).toEqual({ project_ids: null })

    await sync.start([4242])
    expect(backend.bodyOf('/api/sync')).toEqual({ project_ids: [4242] })
    expect(sync.state).toEqual(RUNNING)
    expect(sync.busy).toBe(true)
    expect(sync.statusOf(4242)).toBe('running')
    expect(sync.statusOf(5151)).toBe('queued')
    expect(sync.statusOf(1)).toBe('idle')
  })

  it('cancels', async () => {
    const backend = fakeBackend({
      '/api/sync/cancel': () => Response.json({ ...RUNNING, queue: [], cancelling: true }),
    })
    const sync = useSyncStore()

    await sync.cancel()

    expect(backend.requests()).toEqual(['/api/sync/cancel'])
    expect(sync.state.cancelling).toBe(true)
  })

  it('listens to the backend once', () => {
    const sync = useSyncStore()

    sync.connect()
    sync.connect()

    expect(FakeEventSource.opened.map((source) => source.url)).toEqual(['/api/events'])

    sync.disconnect()

    expect(FakeEventSource.opened[0]!.closed).toBe(true)
  })

  it('follows the progress the backend pushes', () => {
    const sync = useSyncStore()
    sync.connect()

    FakeEventSource.opened[0]!.push({ type: 'sync', state: RUNNING })

    expect(sync.state).toEqual(RUNNING)
  })

  it('reloads the projects when the backend says they changed', async () => {
    const backend = fakeBackend({ '/api/projects': () => Response.json([PROJECT]) })
    const sync = useSyncStore()
    sync.connect()

    FakeEventSource.opened[0]!.push({ type: 'projects' })
    await flushPromises()

    expect(backend.requests()).toEqual(['/api/projects'])
    expect(useProjectsStore().list).toEqual([PROJECT])
  })

  it('checks the account when a sync ends: an expired session signs it out', async () => {
    const expired = { ...SIGNED_OUT, expired: true }
    const backend = fakeBackend({ '/api/account': () => Response.json(expired) })
    const sync = useSyncStore()
    sync.connect()
    const source = FakeEventSource.opened[0]!

    source.push({ type: 'sync', state: RUNNING })
    await flushPromises()
    expect(backend.requests()).toEqual([])

    source.push({ type: 'sync', state: IDLE })
    await flushPromises()

    expect(backend.requests()).toEqual(['/api/account'])
    expect(useAccountStore().info).toEqual(expired)
  })

  it('does without live updates where there is no EventSource', () => {
    vi.stubGlobal('EventSource', undefined)

    expect(() => useSyncStore().connect()).not.toThrow()
  })
})

describe('russianPlural', () => {
  // Messages come as `none | one | few | many`.
  const form = (count: number) => ['нет постов', 'пост', 'поста', 'постов'][russianPlural(count, 4)]

  it('picks the form by the count', () => {
    expect([0, 1, 2, 4, 5, 10].map(form)).toEqual([
      'нет постов',
      'пост',
      'поста',
      'поста',
      'постов',
      'постов',
    ])
    expect([11, 12, 14, 19, 20].map(form)).toEqual([
      'постов',
      'постов',
      'постов',
      'постов',
      'постов',
    ])
    expect([21, 22, 25, 101, 111, 112, 122, 2429].map(form)).toEqual([
      'пост',
      'поста',
      'постов',
      'пост',
      'постов',
      'постов',
      'поста',
      'постов',
    ])
  })

  it('works with three forms too', () => {
    const three = (count: number) => ['пост', 'поста', 'постов'][russianPlural(count, 3)]

    expect([1, 3, 5, 0, 11, 21].map(three)).toEqual([
      'пост',
      'поста',
      'постов',
      'постов',
      'постов',
      'пост',
    ])
  })
})
