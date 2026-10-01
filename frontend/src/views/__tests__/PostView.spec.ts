import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'

import { fakeBackend, media, post } from '@/__tests__/backend'
import { routerAt, withPlugins } from '@/__tests__/mounting'
import { useSyncStore } from '@/stores/sync'
import PostView from '@/views/PostView.vue'

async function mountPost(path = '/posts/9001') {
  const router = await routerAt(path)
  const wrapper = mount(PostView, { ...withPlugins(router), attachTo: document.body })
  await flushPromises()
  return { wrapper, router }
}

beforeEach(() => {
  setActivePinia(createPinia())
})

afterEach(() => {
  document.body.innerHTML = ''
})

describe('PostView', () => {
  it('shows the post: title, date, how long it takes, level, text and tags', async () => {
    fakeBackend({
      '/api/posts/9001': () =>
        Response.json(
          post({
            title: 'Длинное эссе',
            duration_text: 1500,
            tags: [{ id: 71, name: 'Эссе' }],
            html: '<h2>Глава</h2><p>Текст эссе.</p>',
          }),
        ),
    })

    const { wrapper } = await mountPost()

    expect(wrapper.find('h1').text()).toBe('Длинное эссе')
    expect(wrapper.find('.post__meta').text()).toContain('25 минут')
    expect(wrapper.find('.post__meta').text()).toContain('Читатель')
    expect(wrapper.find('.post-body h2').text()).toBe('Глава')
    expect(wrapper.find('.post__tags').text()).toBe('Эссе')
    expect(wrapper.find('.post__back').text()).toBe('Вымышленный альманах')
  })

  it('goes back to the project and to the neighbours', async () => {
    fakeBackend({
      '/api/posts/9001': () =>
        Response.json(
          post({ newer: { id: 9002, title: 'Новее' }, older: { id: 9000, title: 'Старее' } }),
        ),
      '/api/posts/9000': () => Response.json(post({ id: 9000, title: 'Старее' })),
    })
    const { wrapper, router } = await mountPost()

    const [newer, older] = wrapper.findAll('.post__neighbour')
    expect(newer!.text()).toContain('Более новый')
    expect(newer!.text()).toContain('Новее')
    expect(older!.text()).toContain('Более старый')

    await older!.trigger('click')
    await flushPromises()

    expect(router.currentRoute.value.fullPath).toBe('/posts/9000')
    expect(wrapper.find('h1').text()).toBe('Старее')
    // The oldest post has nothing older to go to.
    expect(wrapper.findAll('.post__neighbour')).toHaveLength(0)

    await wrapper.find('.post__back').trigger('click')
    await flushPromises()

    expect(router.currentRoute.value.fullPath).toBe('/projects/4242')
  })

  it('shows a closed post under a lock, with its teaser', async () => {
    fakeBackend({
      '/api/posts/9001': () =>
        Response.json(
          post({
            closed: true,
            html: null,
            text_is_full: false,
            excerpt: 'Анонс закрытого поста.',
            level: { id: 502, name: 'Меценат', price: null },
          }),
        ),
    })

    const { wrapper } = await mountPost()

    expect(wrapper.text()).toContain('Пост закрыт')
    expect(wrapper.text()).toContain('Нужен уровень «Меценат»')
    expect(wrapper.text()).toContain('Анонс закрытого поста.')
    expect(wrapper.find('.post-body').exists()).toBe(false)
  })

  it('explains a copy of a post that is gone or closed on the site', async () => {
    const backend = fakeBackend({
      '/api/posts/9001': () => Response.json(post({ status: 'deleted_on_site' })),
      '/api/posts/9002': () => Response.json(post({ id: 9002, status: 'unavailable' })),
      '/api/posts/9003': () => Response.json(post({ id: 9003, text_is_full: false })),
    })

    const deleted = await mountPost('/posts/9001')
    expect(deleted.wrapper.text()).toContain('На сайте этого поста больше нет')
    // The text is still there to read.
    expect(deleted.wrapper.find('.post-body').text()).toBe('Текст поста.')

    const unavailable = await mountPost('/posts/9002')
    expect(unavailable.wrapper.text()).toContain('Доступ к посту на сайте закрыт')

    const partial = await mountPost('/posts/9003')
    expect(partial.wrapper.text()).toContain('Скачано только начало текста')
    expect(backend.requests()).toHaveLength(3)
  })

  it('lists the audio and the attachments under the text', async () => {
    fakeBackend({
      '/api/posts/9001': () =>
        Response.json(
          post({
            html: '<p>До</p><div class="post-podcast" data-id="6001"></div><p>После</p>',
            media: [
              media({ id: 1, kind: 'audio', source_id: '6001', title: 'Выпуск в тексте' }),
              media({ id: 2, kind: 'audio', source_id: '6002', title: 'Выпуск под текстом' }),
              media({ id: 3, kind: 'attach', source_id: '6003', title: 'Конспект.pdf' }),
            ],
          }),
        ),
    })

    const { wrapper } = await mountPost()
    const sections = wrapper.findAll('.post__section')

    expect(wrapper.find('.post-body').text()).toContain('Выпуск в тексте')
    expect(sections).toHaveLength(2)
    expect(sections[0]!.text()).toContain('Выпуск под текстом')
    // The audio that has its place in the text is not listed a second time.
    expect(sections[0]!.text()).not.toContain('Выпуск в тексте')
    expect(sections[1]!.text()).toContain('Конспект.pdf')
  })

  it('shows a file as soon as it is downloaded', async () => {
    const waiting = post({
      html: '<iframe data-media="9" src="https://kinescope.io/abc"></iframe>',
      media: [media({ id: 9, kind: 'video' })],
    })
    const backend = fakeBackend({ '/api/posts/9001': () => Response.json(waiting) })
    const { wrapper } = await mountPost()
    expect(wrapper.find('video').exists()).toBe(false)

    backend.serve('/api/posts/9001', () =>
      Response.json({
        ...waiting,
        media: [media({ id: 9, kind: 'video', state: 'done', url: '/media/9' })],
      }),
    )
    // Somebody else's file changes nothing here.
    useSyncStore().handle({ type: 'file', kind: 'media', id: 5 })
    await flushPromises()
    expect(wrapper.find('video').exists()).toBe(false)

    useSyncStore().handle({ type: 'file', kind: 'media', id: 9 })
    await flushPromises()

    expect(wrapper.find('video').attributes('src')).toBe('/media/9')
  })

  it('says when there is no such post, or it could not be opened', async () => {
    fakeBackend({ '/api/posts/9002': () => new Response(null, { status: 500 }) })

    const missing = await mountPost('/posts/9001')
    expect(missing.wrapper.text()).toContain('В библиотеке нет такого поста')

    const broken = await mountPost('/posts/9002')
    expect(broken.wrapper.text()).toContain('Не удалось открыть пост')
  })
})
