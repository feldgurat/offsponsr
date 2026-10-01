import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'

import { fakeBackend, media, post } from '@/__tests__/backend'
import { routerAt, withPlugins } from '@/__tests__/mounting'
import type { MediaInfo } from '@/api/types'
import PostBody from '@/components/PostBody.vue'

beforeEach(() => {
  setActivePinia(createPinia())
})

afterEach(() => {
  document.body.innerHTML = ''
})

function body(html: string, files: MediaInfo[] = []) {
  return mount(PostBody, {
    ...withPlugins(),
    props: { html, media: files },
    attachTo: document.body,
  })
}

describe('PostBody', () => {
  it('shows the text with its formatting', () => {
    const wrapper = body(
      '<h2>Заголовок</h2><p class="paragraph-without-indent secret-class">Абзац <b>жирный</b></p><ul><li>пункт</li></ul>',
    )

    expect(wrapper.find('h2').text()).toBe('Заголовок')
    expect(wrapper.find('p b').text()).toBe('жирный')
    expect(wrapper.find('li').text()).toBe('пункт')
    // Only the classes the app knows the meaning of are kept.
    expect(wrapper.find('p').classes()).toEqual(['paragraph-without-indent'])
  })

  it('never lets a script or a handler of the post into the page', () => {
    const wrapper = body(
      '<p onclick="window.hacked = 1" style="position: fixed">Текст</p>' +
        '<script>window.hacked = 2</' +
        'script><img src="https://media.sponsr.ru/a.webp" onerror="window.hacked = 3">',
    )

    expect(wrapper.html()).not.toMatch(/onclick|onerror|script|position/)
    wrapper.find('p').element.click()
    expect((window as { hacked?: number }).hacked).toBeUndefined()
  })

  it('shows a downloaded picture from the library and any other from the web', () => {
    const wrapper = body(
      '<img data-media="7" src="https://media.sponsr.ru/a.webp?1" alt="Первая">' +
        '<img data-media="8" src="https://media.sponsr.ru/b.webp?1">' +
        '<img data-src="/images/c.webp"><img src="javascript:alert(1)">',
      [media({ id: 7, state: 'done', url: '/media/7' }), media({ id: 8 })],
    )

    const pictures = wrapper.findAll('img')
    expect(pictures.map((picture) => picture.attributes('src'))).toEqual([
      '/media/7',
      'https://media.sponsr.ru/b.webp?1',
      'https://sponsr.ru/images/c.webp',
    ])
    expect(pictures[0]!.attributes('alt')).toBe('Первая')
    expect(pictures.every((picture) => picture.attributes('loading') === 'lazy')).toBe(true)
  })

  it('puts the player in place of a downloaded video', () => {
    const wrapper = body(
      '<div class="post-video"><iframe data-media="9" src="https://kinescope.io/abc"></iframe></div>',
      [media({ id: 9, kind: 'video', state: 'done', url: '/media/9' })],
    )

    expect(wrapper.find('iframe').exists()).toBe(false)
    expect(wrapper.find('video').attributes('src')).toBe('/media/9')
  })

  it('offers to download a video that is not in the library', async () => {
    const backend = fakeBackend({ '/api/media/9/download': () => Response.json({ queued: 1 }) })
    const wrapper = body('<iframe data-media="9" src="https://kinescope.io/abc"></iframe>', [
      media({ id: 9, kind: 'video' }),
    ])

    expect(wrapper.find('iframe').exists()).toBe(false)
    expect(wrapper.find('video').exists()).toBe(false)
    expect(wrapper.text()).toContain('Видео ещё не скачано')

    await wrapper.find('button').trigger('click')
    await flushPromises()

    expect(backend.calls()).toEqual(['POST /api/media/9/download'])
    expect(wrapper.text()).toContain('В очереди на скачивание')
  })

  it('frames a player of a known site and only links to an unknown one', () => {
    const wrapper = body(
      '<iframe data-media="3" src="https://www.youtube.com/embed/abc"></iframe>' +
        '<iframe src="https://player.example.org/embed/42"></iframe>',
      [
        media({
          id: 3,
          kind: 'embed',
          state: 'skipped',
          source_url: 'https://www.youtube.com/embed/abc',
        }),
      ],
    )

    const frames = wrapper.findAll('iframe')
    expect(frames).toHaveLength(1)
    expect(frames[0]!.attributes('src')).toBe('https://www.youtube.com/embed/abc')
    // The frame can't navigate the app's window or reach into it.
    expect(frames[0]!.attributes('sandbox')).not.toContain('allow-top-navigation')
    expect(wrapper.text()).toContain('В приложении она не показывается')
    expect(wrapper.findAll('button')).toHaveLength(2)
  })

  it('puts an audio player where the text has a place for it', () => {
    const wrapper = body(
      '<p>До</p><div class="post-podcast" contenteditable="false" data-id="6001"></div><p>После</p>',
      [
        media({
          id: 5,
          kind: 'audio',
          source_id: '6001',
          title: 'Выпуск 12',
          state: 'done',
          url: '/media/5',
        }),
      ],
    )

    expect(wrapper.find('audio').attributes('src')).toBe('/media/5')
    expect(wrapper.text()).toContain('Выпуск 12')
    const order = wrapper.text()
    expect(order.indexOf('До')).toBeLessThan(order.indexOf('Выпуск 12'))
    expect(order.indexOf('Выпуск 12')).toBeLessThan(order.indexOf('После'))
  })

  it('opens an outside link in the browser, not in the window', async () => {
    const backend = fakeBackend({ '/api/open-link': () => new Response(null, { status: 204 }) })
    const wrapper = body('<p><a href="https://example.com/a?b=1" target="_blank">ссылка</a></p>')

    const click = new MouseEvent('click', { bubbles: true, cancelable: true })
    wrapper.find('a').element.dispatchEvent(click)
    await flushPromises()

    expect(click.defaultPrevented).toBe(true)
    expect(backend.bodyOf('/api/open-link')).toEqual({ url: 'https://example.com/a?b=1' })
  })

  it('opens a link to a post of the library inside the app', async () => {
    const backend = fakeBackend({
      '/api/posts/9102': () => Response.json(post({ id: 9102 })),
      '/api/open-link': () => new Response(null, { status: 204 }),
    })
    const router = await routerAt('/posts/9101')
    const wrapper = mount(PostBody, {
      ...withPlugins(router),
      props: { html: '<a href="https://sponsr.ru/fictional-almanac/9102/slug">другой пост</a>' },
      attachTo: document.body,
    })

    wrapper.find('a').element.click()
    await flushPromises()

    expect(router.currentRoute.value.fullPath).toBe('/posts/9102')
    expect(backend.requests()).not.toContain('/api/open-link')
  })

  it('opens a link to a post the library lacks in the browser', async () => {
    const backend = fakeBackend({ '/api/open-link': () => new Response(null, { status: 204 }) })
    const router = await routerAt('/posts/9101')
    const wrapper = mount(PostBody, {
      ...withPlugins(router),
      props: { html: '<a href="/another-project/555/">чужой пост</a>' },
      attachTo: document.body,
    })

    wrapper.find('a').element.click()
    await flushPromises()

    expect(router.currentRoute.value.fullPath).toBe('/posts/9101')
    expect(backend.bodyOf('/api/open-link')).toEqual({
      url: 'https://sponsr.ru/another-project/555/',
    })
  })

  it('goes nowhere on a link it has no business following', async () => {
    const backend = fakeBackend()
    const wrapper = body('<a href="file:///C:/Windows/system32/calc.exe">ловушка</a>')

    wrapper.find('a').element.click()
    await flushPromises()

    expect(backend.requests()).toEqual([])
  })
})
