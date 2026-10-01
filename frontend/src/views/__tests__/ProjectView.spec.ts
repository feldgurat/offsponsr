import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { Router } from 'vue-router'

import {
  card,
  fakeBackend,
  feedPage,
  media,
  post,
  PROJECT,
  SETTINGS,
  SIGNED_IN,
} from '@/__tests__/backend'
import { buttonIn, routerAt, withPlugins } from '@/__tests__/mounting'
import type { PostCard } from '@/api/types'
import { useAccountStore } from '@/stores/account'
import { useSettingsStore } from '@/stores/settings'
import { useSyncStore } from '@/stores/sync'
import ProjectView from '@/views/ProjectView.vue'

const FEED = '/api/projects/4242/posts'

/** `count` posts numbered from the newest, as the backend would page them. */
function numbered(count: number): PostCard[] {
  return Array.from({ length: count }, (_, index) =>
    card({ id: 9000 - index, title: `Пост ${index + 1}` }),
  )
}

/** A backend with the project and a feed of `posts`, served 20 to a page. */
function backendWith(posts: PostCard[], replies: Parameters<typeof fakeBackend>[0] = {}) {
  return fakeBackend({
    '/api/projects': () => Response.json([PROJECT]),
    [FEED]: (url) => {
      const page = Number(url.searchParams.get('page'))
      const withText = url.searchParams.get('with_text') === 'true'
      const slice = posts
        .slice((page - 1) * 20, page * 20)
        .map((item) => (withText ? { ...item, html: `<p>Текст поста «${item.title}».</p>` } : item))
      return Response.json(feedPage(slice, { total: posts.length, page }))
    },
    '/api/settings': (_url, init) =>
      Response.json({ ...SETTINGS, ...JSON.parse(String(init?.body ?? '{}')) }),
    ...replies,
  })
}

async function mountProject(path = '/projects/4242'): Promise<{
  wrapper: ReturnType<typeof mount>
  router: Router
}> {
  const router = await routerAt(path)
  const wrapper = mount(ProjectView, { ...withPlugins(router), attachTo: document.body })
  await flushPromises()
  return { wrapper, router }
}

function feedRequests(backend: ReturnType<typeof fakeBackend>): URLSearchParams[] {
  return backend
    .requests()
    .filter((address) => address.startsWith(FEED))
    .map((address) => new URL(address, 'http://127.0.0.1').searchParams)
}

function titles(wrapper: ReturnType<typeof mount>): string[] {
  return wrapper.findAll('.feed-post__title, .feed-row__title').map((title) => title.text())
}

beforeEach(() => {
  setActivePinia(createPinia())
})

afterEach(() => {
  vi.restoreAllMocks()
  document.body.innerHTML = ''
})

describe('ProjectView', () => {
  it('shows the project and its posts as a stream of texts', async () => {
    const backend = backendWith(numbered(3))

    const { wrapper } = await mountProject()

    expect(wrapper.find('h1').text()).toBe('Вымышленный альманах')
    expect(wrapper.find('.project__logo').attributes('src')).toBe('/media/projects/4242/logo')
    expect(wrapper.find('.project__cover').attributes('src')).toBe('/media/projects/4242/cover')
    expect(wrapper.text()).toContain('22 поста')
    expect(wrapper.text()).toContain('закрытых: 1')
    expect(titles(wrapper)).toEqual(['Пост 1', 'Пост 2', 'Пост 3'])
    expect(wrapper.text()).toContain('Текст поста «Пост 1».')
    const [request] = feedRequests(backend)
    expect(Object.fromEntries(request!)).toEqual({
      order: 'desc',
      hide_closed: 'false',
      hide_deleted: 'false',
      with_text: 'true',
      page: '1',
    })
    expect(wrapper.text()).not.toContain('Показать ещё')
  })

  it('cuts a long text in the stream and opens it in place', async () => {
    backendWith(numbered(1))
    vi.spyOn(HTMLElement.prototype, 'scrollHeight', 'get').mockReturnValue(1500)
    vi.spyOn(HTMLElement.prototype, 'clientHeight', 'get').mockReturnValue(420)

    const { wrapper } = await mountProject()

    expect(wrapper.find('.feed-post__text--collapsed').exists()).toBe(true)
    buttonIn(wrapper.element, 'Развернуть').click()
    await flushPromises()

    expect(wrapper.find('.feed-post__text--collapsed').exists()).toBe(false)
    expect(buttonIn(wrapper.element, 'Свернуть')).toBeTruthy()
  })

  it('offers no «Развернуть» for a text that fits', async () => {
    backendWith(numbered(1))

    const { wrapper } = await mountProject()

    expect(wrapper.text()).not.toContain('Развернуть')
    expect(wrapper.text()).toContain('Перейти в пост')
  })

  it('remembers the chosen view and asks for texts only in the stream', async () => {
    const backend = backendWith(numbered(2))
    const { wrapper } = await mountProject()

    await wrapper.find('input[value="list"]').setValue(true)
    await flushPromises()

    expect(backend.bodyOf('/api/settings')).toEqual({ feed_view: 'list' })
    expect(wrapper.findAll('.feed-row')).toHaveLength(2)
    expect(feedRequests(backend).map((params) => params.get('with_text'))).toEqual([
      'true',
      'false',
    ])

    // The tiles show the same posts: nothing is fetched again.
    await wrapper.find('input[value="tile"]').setValue(true)
    await flushPromises()

    expect(wrapper.findAll('.feed-post--tile')).toHaveLength(2)
    expect(feedRequests(backend)).toHaveLength(2)
  })

  it('takes the filters from the address', async () => {
    const backend = backendWith(numbered(1))

    await mountProject(
      '/projects/4242?order=asc&content=video&from=2026-09-01&to=2026-09-30&deleted=hide',
    )

    const [request] = feedRequests(backend)
    expect(request!.get('order')).toBe('asc')
    expect(request!.get('content')).toBe('video')
    expect(request!.get('hide_deleted')).toBe('true')
    // The days are the user's: from the first moment of one to the last moment of the other.
    expect(request!.get('date_from')).toBe(new Date(2026, 8, 1).toISOString())
    expect(request!.get('date_to')).toBe(new Date(2026, 8, 30, 23, 59, 59, 999).toISOString())
  })

  it('ignores nonsense in the address', async () => {
    const backend = backendWith(numbered(1))

    await mountProject('/projects/4242?order=sideways&content=smell&from=yesterday&page=-3')

    const [request] = feedRequests(backend)
    expect(Object.fromEntries(request!)).toMatchObject({ order: 'desc', page: '1' })
    expect(request!.has('content')).toBe(false)
    expect(request!.has('date_from')).toBe(false)
  })

  it('hides the closed posts for good once asked to', async () => {
    const backend = backendWith(numbered(2))
    const { wrapper } = await mountProject()
    buttonIn(wrapper.element, 'Фильтры').click()
    await flushPromises()

    const [hideClosed, hideDeleted] = wrapper.findAll('input[type="checkbox"]')
    await hideClosed!.setValue(true)
    await flushPromises()

    expect(backend.bodyOf('/api/settings')).toEqual({ hide_closed: true })
    expect(feedRequests(backend).at(-1)!.get('hide_closed')).toBe('true')

    // «Скрыть удалённые» belongs to this visit and lives in the address.
    await hideDeleted!.setValue(true)
    await flushPromises()

    expect(feedRequests(backend).at(-1)!.get('hide_deleted')).toBe('true')
  })

  it('shows more posts under the ones on screen, and goes to a page', async () => {
    const backend = backendWith(numbered(45))
    useSettingsStore().values = { ...SETTINGS, feed_view: 'list' }
    const { wrapper, router } = await mountProject()

    expect(titles(wrapper)).toHaveLength(20)

    buttonIn(wrapper.element, 'Показать ещё').click()
    await flushPromises()

    expect(router.currentRoute.value.query).toEqual({ upto: '2' })
    expect(titles(wrapper)).toHaveLength(40)
    expect(feedRequests(backend).map((params) => params.get('page'))).toEqual(['1', '2'])

    await wrapper.find('.ant-pagination-item-3').trigger('click')
    await flushPromises()

    expect(router.currentRoute.value.query).toEqual({ page: '3' })
    expect(titles(wrapper)).toEqual(['Пост 41', 'Пост 42', 'Пост 43', 'Пост 44', 'Пост 45'])
    expect(wrapper.text()).not.toContain('Показать ещё')
  })

  it('comes back from a post to the pages that were on screen, without loading them again', async () => {
    const backend = backendWith(numbered(45))
    useSettingsStore().values = { ...SETTINGS, feed_view: 'list' }
    const first = await mountProject('/projects/4242?upto=2')
    expect(titles(first.wrapper)).toHaveLength(40)
    first.wrapper.unmount()

    const second = await mountProject('/projects/4242?upto=2')

    expect(titles(second.wrapper)).toHaveLength(40)
    expect(feedRequests(backend)).toHaveLength(2)
  })

  it('shows a closed post under a lock with the level it needs', async () => {
    backendWith([
      card({
        id: 1,
        title: 'Закрытый материал',
        closed: true,
        text_is_full: false,
        excerpt: 'Анонс закрытого поста.',
        level: { id: 502, name: 'Меценат', price: 1500 },
      }),
    ])
    useSettingsStore().values = { ...SETTINGS, feed_view: 'feed' }

    const { wrapper } = await mountProject()

    expect(wrapper.text()).toContain(
      `Нужен уровень «Меценат» · ${(1500).toLocaleString('ru')} ₽ в месяц`,
    )
    expect(wrapper.text()).toContain('Анонс закрытого поста.')
    expect(wrapper.text()).not.toContain('Читать далее')
  })

  it('marks what has happened to a post on the site', async () => {
    backendWith([
      card({ id: 1, status: 'deleted_on_site' }),
      card({ id: 2, status: 'unavailable' }),
      card({ id: 3, text_is_full: false }),
      card({ id: 4, level: null, pinned: true }),
    ])
    useSettingsStore().values = { ...SETTINGS, feed_view: 'feed' }

    const { wrapper } = await mountProject()
    const cards = wrapper.findAll('.feed-post').map((item) => item.text())

    expect(cards[0]).toContain('Удалён на сайте')
    expect(cards[1]).toContain('Доступ закрыт')
    expect(cards[2]).toContain('Только начало текста')
    expect(cards[3]).toContain('Закреплён')
    expect(cards[3]).toContain('Бесплатный')
  })

  it('shows the players of audio in the stream, a few of them', async () => {
    const audio = [1, 2, 3, 4, 5].map((id) =>
      media({
        id,
        kind: 'audio',
        source_id: String(6000 + id),
        title: `Выпуск ${id}`,
        state: 'done',
        url: `/media/${id}`,
      }),
    )
    backendWith([card({ media: [...audio, media({ id: 9, kind: 'attach' })] })])

    const { wrapper } = await mountProject()

    expect(wrapper.findAll('audio')).toHaveLength(3)
    expect(wrapper.text()).toContain('Ещё аудио в посте: 2')
    expect(wrapper.text()).toContain('Вложений в посте: 1')
  })

  it('says so when the filters leave nothing', async () => {
    backendWith([])

    const filtered = await mountProject('/projects/4242?content=video')
    expect(filtered.wrapper.text()).toContain('Под эти фильтры ничего не подходит')
    filtered.wrapper.unmount()

    const plain = await mountProject()
    expect(plain.wrapper.text()).toContain('В проекте пока нет постов')
  })

  it('reports a feed that failed to load', async () => {
    backendWith([], { [FEED]: () => new Response(null, { status: 500 }) })

    const { wrapper } = await mountProject()

    expect(wrapper.text()).toContain('Не удалось загрузить посты')
  })

  it('says when there is no such project', async () => {
    fakeBackend({ '/api/projects': () => Response.json([PROJECT]) })

    const { wrapper } = await mountProject('/projects/777')

    expect(wrapper.text()).toContain('В библиотеке нет такого проекта')
  })

  it('updates the project when signed in', async () => {
    const backend = backendWith(numbered(1), {
      '/api/sync': () =>
        Response.json({ running: null, queue: [4242], failures: [], cancelling: false }),
    })
    useAccountStore().info = SIGNED_IN
    const { wrapper } = await mountProject()

    buttonIn(wrapper.element, 'Обновить').click()
    await flushPromises()

    expect(backend.bodyOf('/api/sync')).toEqual({ project_ids: [4242] })
    expect(wrapper.find('.project__head').text()).toContain('В очереди')
  })

  it('shows a cover as soon as it is downloaded', async () => {
    const backend = backendWith(numbered(2), {
      '/api/posts/9000': () =>
        Response.json(post({ id: 9000, title: 'Пост 1', cover: '/media/posts/9000/cover' })),
    })
    useSettingsStore().values = { ...SETTINGS, feed_view: 'tile' }
    const { wrapper } = await mountProject()
    expect(wrapper.find('.post-cover__image').exists()).toBe(false)

    useSyncStore().handle({ type: 'file', kind: 'post_cover', id: 9000 })
    // A cover of a post that isn't on screen is nobody's business here.
    useSyncStore().handle({ type: 'file', kind: 'post_cover', id: 1 })
    await flushPromises()

    expect(wrapper.find('.post-cover__image').attributes('src')).toBe('/media/posts/9000/cover')
    expect(backend.requests().filter((address) => address.startsWith('/api/posts/'))).toEqual([
      '/api/posts/9000',
    ])
  })

  it('loads the feed again after the project has been synced', async () => {
    const backend = backendWith(numbered(1))
    const { wrapper } = await mountProject()

    backend.serve('/api/projects', () =>
      Response.json([{ ...PROJECT, last_synced_at: '2026-10-02T10:00:00Z' }]),
    )
    backend.serve(FEED, () => Response.json(feedPage([card({ id: 1, title: 'Свежий пост' })])))
    useSyncStore().handle({ type: 'projects' })
    await flushPromises()

    expect(titles(wrapper)).toEqual(['Свежий пост'])
  })

  describe('project settings', () => {
    async function openSettings(replies: Parameters<typeof fakeBackend>[0]) {
      const backend = backendWith(numbered(1), replies)
      const { wrapper } = await mountProject()
      await wrapper.find('button[aria-label="Настройки проекта"]').trigger('click')
      await flushPromises()
      return { backend, wrapper }
    }

    const NOTHING = { files: 0, bytes: 0, files_without_size: 0 }

    it('saves a change at once', async () => {
      const { backend } = await openSettings({
        '/api/projects/4242': () =>
          Response.json({ project: { ...PROJECT, sync_enabled: false }, to_download: NOTHING }),
      })

      document.body.querySelector<HTMLButtonElement>('.ant-modal button[role="switch"]')!.click()
      await flushPromises()

      expect(backend.bodyOf('/api/projects/4242')).toEqual({ sync_enabled: false })
      expect(backend.calls()).toContain('PATCH /api/projects/4242')
      expect(document.body.textContent).not.toContain('Скачать сейчас?')
    })

    it('asks before downloading what a kind switched to «сразу» has waiting', async () => {
      const { backend, wrapper } = await openSettings({
        '/api/projects/4242': () =>
          Response.json({
            project: { ...PROJECT, media_mode_video: 'auto' },
            to_download: { files: 12, bytes: 3 * 1024 ** 3, files_without_size: 5 },
          }),
        '/api/projects/4242/download': () => Response.json({ queued: 12 }),
      })

      const [, video] = wrapper.findAllComponents({ name: 'ASelect' }).slice(-4)
      video!.vm.$emit('change', 'auto')
      await flushPromises()

      expect(backend.bodyOf('/api/projects/4242')).toEqual({ media_mode_video: 'auto' })
      expect(document.body.textContent).toContain('Скачать сейчас?')
      expect(document.body.textContent).toContain('В проекте 12 ещё не скачанных файлов.')
      expect(document.body.textContent).toContain('Известный объём — 3 ГБ.')
      expect(document.body.textContent).toContain('Файлов, размер которых заранее неизвестен: 5.')
      expect(backend.calls()).not.toContain('POST /api/projects/4242/download')

      buttonIn(document.body, 'Скачать').click()
      await flushPromises()

      expect(backend.calls()).toContain('POST /api/projects/4242/download')
    })

    it('sends «лучшее» as no limit on the quality', async () => {
      const { backend, wrapper } = await openSettings({
        '/api/projects/4242': () => Response.json({ project: PROJECT, to_download: NOTHING }),
      })
      const quality = wrapper.findAllComponents({ name: 'ASelect' }).at(-1)!

      quality.vm.$emit('change', 720)
      await flushPromises()
      expect(backend.bodyOf('/api/projects/4242')).toEqual({ video_quality: 720 })

      quality.vm.$emit('change', 0)
      await flushPromises()
      expect(backend.bodyOf('/api/projects/4242')).toEqual({ video_quality: null })
    })

    it('says when a setting could not be saved', async () => {
      await openSettings({ '/api/projects/4242': () => new Response(null, { status: 500 }) })

      document.body.querySelector<HTMLButtonElement>('.ant-modal button[role="switch"]')!.click()
      await flushPromises()

      expect(document.body.textContent).toContain('Не удалось сохранить настройку.')
    })
  })
})
