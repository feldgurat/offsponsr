import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { fakeBackend, ffmpeg, media, NO_FFMPEG } from '@/__tests__/backend'
import { buttonIn, withPlugins } from '@/__tests__/mounting'
import EmbedFrame from '@/components/EmbedFrame.vue'
import MediaAttachment from '@/components/MediaAttachment.vue'
import MediaAudio from '@/components/MediaAudio.vue'
import MediaDownload from '@/components/MediaDownload.vue'
import MediaVideo from '@/components/MediaVideo.vue'
import { useDownloadsStore } from '@/stores/downloads'
import { useMediaStore } from '@/stores/media'
import { useSyncStore } from '@/stores/sync'

beforeEach(() => {
  setActivePinia(createPinia())
})

afterEach(() => {
  vi.restoreAllMocks()
  document.body.innerHTML = ''
})

describe('MediaDownload', () => {
  it('offers the download with the size, if the site told it', () => {
    const sized = mount(MediaDownload, {
      ...withPlugins(),
      props: { media: media({ kind: 'audio', size: 48_211_234 }) },
    })
    const unsized = mount(MediaDownload, { ...withPlugins(), props: { media: media() } })

    expect(sized.text()).toBe('Скачать · 46 МБ')
    expect(unsized.text()).toBe('Скачать')
  })

  it('queues the file and says so before the backend does', async () => {
    const backend = fakeBackend({ '/api/media/5/download': () => Response.json({ queued: 1 }) })
    const wrapper = mount(MediaDownload, { ...withPlugins(), props: { media: media({ id: 5 }) } })

    await wrapper.find('button').trigger('click')
    await flushPromises()

    expect(backend.calls()).toEqual(['POST /api/media/5/download'])
    expect(wrapper.text()).toBe('В очереди на скачивание')
    expect(wrapper.find('button').exists()).toBe(false)
  })

  it('offers the download again if it could not be queued', async () => {
    fakeBackend()
    const wrapper = mount(MediaDownload, { ...withPlugins(), props: { media: media({ id: 5 }) } })

    await wrapper.find('button').trigger('click')
    await flushPromises()

    expect(wrapper.text()).toBe('Скачать')
  })

  it('shows the bytes arriving', () => {
    useDownloadsStore().state = {
      active: [{ key: 'media-5', title: 'Выпуск', bytes_done: 1_048_576, bytes_total: 4_194_304 }],
      queued: 0,
      done: 0,
      failed: 0,
      cancelling: false,
    }

    const wrapper = mount(MediaDownload, {
      ...withPlugins(),
      props: { media: media({ id: 5, state: 'downloading' }) },
    })

    expect(wrapper.text()).toContain('1 МБ из 4 МБ')
    expect(wrapper.find('button').exists()).toBe(false)
  })

  it('explains a failure and offers to try again', async () => {
    const backend = fakeBackend({ '/api/media/5/download': () => Response.json({ queued: 1 }) })
    const wrapper = mount(MediaDownload, {
      ...withPlugins(),
      props: { media: media({ id: 5, state: 'error', error: 'no_ffmpeg' }) },
    })
    const unknown = mount(MediaDownload, {
      ...withPlugins(),
      props: { media: media({ id: 6, state: 'error', error: 'brand_new_code' }) },
    })

    expect(wrapper.text()).toContain('Не найден ffmpeg')
    expect(unknown.text()).toContain('Не удалось скачать')

    buttonIn(wrapper.element, 'Повторить').click()
    await flushPromises()

    expect(backend.calls()).toContain('POST /api/media/5/download')
  })

  it('offers to install ffmpeg where a video failed for the lack of it', async () => {
    fakeBackend({ '/api/ffmpeg': () => Response.json(NO_FFMPEG) })
    const video = mount(MediaDownload, {
      ...withPlugins(),
      props: { media: media({ id: 5, kind: 'video', state: 'error', error: 'no_ffmpeg' }) },
    })
    const other = mount(MediaDownload, {
      ...withPlugins(),
      props: { media: media({ id: 6, kind: 'video', state: 'error', error: 'player_changed' }) },
    })
    await flushPromises()

    expect(buttonIn(video.element, 'Установить ffmpeg')).toBeTruthy()
    expect(other.text()).not.toContain('Установить ffmpeg')

    // Once there is an ffmpeg, only trying again is left.
    useSyncStore().handle({ type: 'ffmpeg', state: ffmpeg() })
    await flushPromises()

    expect(video.text()).not.toContain('Установить ffmpeg')
    expect(buttonIn(video.element, 'Повторить')).toBeTruthy()
  })

  it('forgets the click once the backend reports the file', async () => {
    fakeBackend({ '/api/media/5/download': () => Response.json({ queued: 1 }) })
    const wrapper = mount(MediaDownload, { ...withPlugins(), props: { media: media({ id: 5 }) } })
    await wrapper.find('button').trigger('click')
    await flushPromises()

    // The download was cancelled: the row is back to pending and the event says it is through.
    useSyncStore().handle({ type: 'file', kind: 'media', id: 5 })
    await flushPromises()

    expect(useMediaStore().requested.has(5)).toBe(false)
    expect(wrapper.text()).toBe('Скачать')
  })
})

describe('MediaVideo', () => {
  it('plays a downloaded video and shows where it is', async () => {
    const backend = fakeBackend({
      '/api/media/9/reveal': () => new Response(null, { status: 204 }),
    })
    const wrapper = mount(MediaVideo, {
      ...withPlugins(),
      props: { media: media({ id: 9, kind: 'video', state: 'done', url: '/media/9' }) },
    })

    expect(wrapper.find('video').attributes()).toMatchObject({
      src: '/media/9',
      preload: 'metadata',
    })

    buttonIn(wrapper.element, 'Показать в папке').click()
    await flushPromises()
    expect(backend.calls()).toEqual(['POST /api/media/9/reveal'])
  })
})

describe('MediaAudio', () => {
  it('shows the name, the length and the size, and plays what is downloaded', () => {
    const wrapper = mount(MediaAudio, {
      ...withPlugins(),
      props: {
        media: media({
          id: 5,
          kind: 'audio',
          title: 'Альманах, выпуск 12',
          duration: 3725,
          size: 48_211_234,
          state: 'done',
          url: '/media/5',
        }),
      },
    })

    expect(wrapper.text()).toContain('Альманах, выпуск 12')
    expect(wrapper.text()).toContain('1:02:05 · 46 МБ')
    // Nothing is read from the disk until the user presses play.
    expect(wrapper.find('audio').attributes()).toMatchObject({ src: '/media/5', preload: 'none' })
  })

  it('offers to download what is not in the library', () => {
    const wrapper = mount(MediaAudio, {
      ...withPlugins(),
      props: { media: media({ id: 5, kind: 'audio', title: null, duration: 65, size: 1024 }) },
    })

    expect(wrapper.find('audio').exists()).toBe(false)
    expect(wrapper.text()).toContain('Аудио')
    expect(wrapper.text()).toContain('1:05 · 1 КБ')
    expect(wrapper.text()).toContain('Скачать')
  })
})

describe('MediaAttachment', () => {
  it('opens a downloaded document and shows it in its folder', async () => {
    const backend = fakeBackend({
      '/api/media/7/open': () => new Response(null, { status: 204 }),
      '/api/media/7/reveal': () => new Response(null, { status: 204 }),
    })
    const wrapper = mount(MediaAttachment, {
      ...withPlugins(),
      props: {
        media: media({
          id: 7,
          kind: 'attach',
          title: 'Конспект.pdf',
          size: 482_113,
          state: 'done',
          file_name: 'Конспект.pdf',
          can_open: true,
        }),
      },
    })

    expect(wrapper.text()).toContain('Конспект.pdf')
    expect(wrapper.text()).toContain('471 КБ')
    buttonIn(wrapper.element, 'Открыть').click()
    buttonIn(wrapper.element, 'Показать в папке').click()
    await flushPromises()

    expect(backend.calls()).toEqual(['POST /api/media/7/open', 'POST /api/media/7/reveal'])
  })

  it('only shows a program or an archive in its folder', () => {
    const wrapper = mount(MediaAttachment, {
      ...withPlugins(),
      props: { media: media({ id: 7, kind: 'attach', title: 'setup.exe', state: 'done' }) },
    })

    const labels = wrapper.findAll('button').map((button) => button.text())
    expect(labels).toEqual(['Показать в папке'])
  })

  it('offers to download a file that is not in the library', () => {
    const wrapper = mount(MediaAttachment, {
      ...withPlugins(),
      props: { media: media({ id: 7, kind: 'attach', title: 'Конспект.pdf', size: 2048 }) },
    })

    expect(wrapper.text()).toContain('Скачать')
    expect(wrapper.text()).not.toContain('Показать в папке')
  })
})

describe('EmbedFrame', () => {
  it('frames a known player while online', () => {
    const wrapper = mount(EmbedFrame, {
      ...withPlugins(),
      props: { src: 'https://www.youtube.com/embed/abc' },
    })

    expect(wrapper.find('iframe').attributes('src')).toBe('https://www.youtube.com/embed/abc')
    expect(wrapper.find('iframe').attributes('sandbox')).toBe(
      'allow-scripts allow-same-origin allow-presentation allow-popups',
    )
  })

  it('shows a link instead of the frame while offline', async () => {
    vi.spyOn(navigator, 'onLine', 'get').mockReturnValue(false)
    const backend = fakeBackend({ '/api/open-link': () => new Response(null, { status: 204 }) })
    const wrapper = mount(EmbedFrame, {
      ...withPlugins(),
      props: { src: 'https://www.youtube.com/embed/abc' },
    })

    expect(wrapper.find('iframe').exists()).toBe(false)
    expect(wrapper.text()).toContain('только при подключении к интернету')

    buttonIn(wrapper.element, 'Открыть в браузере').click()
    await flushPromises()
    expect(backend.bodyOf('/api/open-link')).toEqual({ url: 'https://www.youtube.com/embed/abc' })
  })

  it('never frames an unknown site', () => {
    const wrapper = mount(EmbedFrame, {
      ...withPlugins(),
      props: { src: 'https://player.example.org/embed/42' },
    })

    expect(wrapper.find('iframe').exists()).toBe(false)
    expect(wrapper.text()).toContain('В приложении она не показывается')
  })

  it('offers no link for an address that is not a web address', () => {
    const wrapper = mount(EmbedFrame, { ...withPlugins(), props: { src: 'javascript:alert(1)' } })

    expect(wrapper.find('iframe').exists()).toBe(false)
    expect(wrapper.find('button').exists()).toBe(false)
  })
})
