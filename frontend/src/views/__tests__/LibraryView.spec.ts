import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'

import { fakeBackend, IDLE, PROJECT, SIGNED_IN, SUBSCRIPTION } from '@/__tests__/backend'
import AddProjectsModal from '@/components/AddProjectsModal.vue'
import SyncPanel from '@/components/SyncPanel.vue'
import { i18n } from '@/i18n'
import { useAccountStore } from '@/stores/account'
import { useProjectsStore } from '@/stores/projects'
import { useSyncStore } from '@/stores/sync'
import LibraryView from '@/views/LibraryView.vue'

const plugins = { global: { plugins: [i18n] } }

function buttonIn(root: ParentNode, label: string): HTMLButtonElement {
  const found = [...root.querySelectorAll('button')].find(
    (candidate) => candidate.textContent?.trim() === label,
  )
  if (!found) {
    throw new Error(`No button labelled "${label}"`)
  }
  return found
}

async function mountLibrary() {
  const wrapper = mount(LibraryView, { ...plugins, attachTo: document.body })
  await flushPromises()
  return wrapper
}

beforeEach(() => {
  setActivePinia(createPinia())
})

afterEach(() => {
  document.body.innerHTML = ''
})

describe('LibraryView', () => {
  it('suggests signing in while signed out', async () => {
    fakeBackend()

    const wrapper = await mountLibrary()

    expect(wrapper.text()).toContain('В библиотеке пока нет проектов')
    expect(wrapper.text()).toContain('Войдите в sponsr.ru, чтобы добавить проекты')
    expect(wrapper.text()).not.toContain('Добавить проекты')
  })

  it('suggests adding projects once signed in', async () => {
    fakeBackend()
    useAccountStore().info = SIGNED_IN

    const wrapper = await mountLibrary()

    expect(wrapper.text()).toContain('Добавьте проекты из ваших подписок или по ссылке.')
    expect(wrapper.text()).not.toContain('Войдите в sponsr.ru')
    expect(wrapper.text()).not.toContain('Обновить всё')
  })

  it('lists the projects with their numbers', async () => {
    fakeBackend({
      '/api/projects': () =>
        Response.json([
          PROJECT,
          { ...PROJECT, id: 5151, title: 'Второй проект', posts: 1, last_synced_at: null },
          { ...PROJECT, id: 6161, title: 'Третий проект', posts: 105, posts_without_text: 3 },
        ]),
    })
    useAccountStore().info = SIGNED_IN

    const wrapper = await mountLibrary()
    const rows = wrapper.findAll('.library__project').map((row) => row.text())

    expect(rows[0]).toContain('Вымышленный альманах')
    expect(rows[0]).toContain('22 поста')
    const when = new Intl.DateTimeFormat('ru', { dateStyle: 'medium', timeStyle: 'short' }).format(
      new Date(PROJECT.last_synced_at!),
    )
    expect(rows[0]).toContain(`обновлён ${when}`)
    expect(rows[1]).toContain('1 пост')
    expect(rows[1]).toContain('ещё не скачан')
    expect(rows[2]).toContain('105 постов')
    expect(rows[2]).toContain('без полного текста: 3')
    expect(wrapper.text()).not.toContain('В библиотеке пока нет проектов')
  })

  it('updates one project or all of them', async () => {
    const backend = fakeBackend({
      '/api/projects': () => Response.json([PROJECT]),
      '/api/sync': () => Response.json(IDLE),
    })
    useAccountStore().info = SIGNED_IN
    const wrapper = await mountLibrary()

    buttonIn(wrapper.element, 'Обновить').click()
    await flushPromises()
    expect(backend.bodyOf('/api/sync')).toEqual({ project_ids: [4242] })

    buttonIn(wrapper.element, 'Обновить всё').click()
    await flushPromises()
    expect(backend.bodyOf('/api/sync')).toEqual({ project_ids: null })
  })

  it('shows what is being updated instead of the buttons', async () => {
    fakeBackend({
      '/api/projects': () =>
        Response.json([PROJECT, { ...PROJECT, id: 5151, title: 'Второй проект' }]),
    })
    useAccountStore().info = SIGNED_IN
    useSyncStore().state = {
      ...IDLE,
      running: { project_id: 4242, title: PROJECT.title, posts_done: 20, posts_total: 45 },
      queue: [5151],
    }

    const wrapper = await mountLibrary()
    const rows = wrapper.findAll('.library__project').map((row) => row.text())

    expect(rows[0]).toContain('Обновляется')
    expect(rows[1]).toContain('В очереди')
    expect(wrapper.findAll('.library__project button')).toHaveLength(0)
    expect(buttonIn(wrapper.element, 'Обновить всё').disabled).toBe(true)
  })

  it('keeps the library readable when signed out: no update buttons', async () => {
    fakeBackend({ '/api/projects': () => Response.json([PROJECT]) })

    const wrapper = await mountLibrary()

    expect(wrapper.text()).toContain('Вымышленный альманах')
    expect(wrapper.findAll('.library__project button')).toHaveLength(0)
    expect(wrapper.text()).not.toContain('Обновить всё')
  })
})

describe('SyncPanel', () => {
  it('is not there when nothing happens', () => {
    expect(mount(SyncPanel, plugins).text()).toBe('')
  })

  it('shows the progress and the queue', () => {
    useSyncStore().state = {
      ...IDLE,
      running: { project_id: 4242, title: PROJECT.title, posts_done: 20, posts_total: 45 },
      queue: [5151, 6161],
    }

    const text = mount(SyncPanel, plugins).text()

    expect(text).toContain('Обновляется: Вымышленный альманах')
    expect(text).toContain('20 из 45 постов')
    expect(text).toContain('44%')
    expect(text).toContain('В очереди: 2')
  })

  it('says it is preparing before the post count is known', () => {
    useSyncStore().state = {
      ...IDLE,
      running: { project_id: 4242, title: PROJECT.title, posts_done: 0, posts_total: null },
    }

    expect(mount(SyncPanel, plugins).text()).toContain('Подготовка…')
  })

  it('cancels', async () => {
    const backend = fakeBackend({ '/api/sync/cancel': () => Response.json(IDLE) })
    useSyncStore().state = {
      ...IDLE,
      running: { project_id: 4242, title: PROJECT.title, posts_done: 0, posts_total: null },
    }
    const wrapper = mount(SyncPanel, plugins)

    buttonIn(wrapper.element, 'Отменить').click()
    await flushPromises()

    expect(backend.requests()).toContain('/api/sync/cancel')
    expect(wrapper.text()).toBe('')
  })

  it('explains what failed', () => {
    useSyncStore().state = {
      ...IDLE,
      failures: [
        { project_id: 4242, title: PROJECT.title, code: 'session_expired' },
        { project_id: 5151, title: 'Второй проект', code: 'brand_new_code' },
      ],
    }

    const text = mount(SyncPanel, plugins).text()

    expect(text).toContain('Не удалось обновить «Вымышленный альманах»')
    expect(text).toContain('Сессия sponsr.ru истекла')
    expect(text).toContain('Не удалось обновить «Второй проект»')
    expect(text).toContain('Неизвестная ошибка')
  })
})

describe('AddProjectsModal', () => {
  async function openModal() {
    const wrapper = mount(AddProjectsModal, {
      ...plugins,
      props: { open: false, 'onUpdate:open': (open: boolean) => wrapper.setProps({ open }) },
      attachTo: document.body,
    })
    await wrapper.setProps({ open: true })
    await flushPromises()
    return wrapper
  }

  function checkboxes(): HTMLInputElement[] {
    return [...document.body.querySelectorAll<HTMLInputElement>('input[type="checkbox"]')]
  }

  async function typeAddress(text: string) {
    const input = document.body.querySelector<HTMLInputElement>('input[type="text"]')!
    input.value = text
    input.dispatchEvent(new Event('input'))
    await flushPromises()
  }

  it('offers the subscriptions that are not in the library yet', async () => {
    fakeBackend({
      '/api/subscriptions': () =>
        Response.json([
          SUBSCRIPTION,
          { ...SUBSCRIPTION, id: 5151, title: 'Уже добавленный', in_library: true },
        ]),
    })
    const wrapper = await openModal()

    expect(document.body.textContent).toContain('Вымышленный альманах')
    expect(document.body.textContent).toContain('Читатель')
    expect(document.body.textContent).toContain('уже в библиотеке')
    const [fresh, present] = checkboxes()
    expect([fresh!.checked, fresh!.disabled]).toEqual([false, false])
    expect([present!.checked, present!.disabled]).toEqual([true, true])
    expect(buttonIn(document.body, 'Добавить и скачать').disabled).toBe(true)

    wrapper.unmount()
  })

  it('adds the chosen subscriptions and closes', async () => {
    const backend = fakeBackend({
      '/api/subscriptions': () => Response.json([SUBSCRIPTION]),
      '/api/projects': () => Response.json([PROJECT]),
    })
    const wrapper = await openModal()

    checkboxes()[0]!.click()
    await flushPromises()
    buttonIn(document.body, 'Добавить и скачать').click()
    await flushPromises()

    expect(backend.bodyOf('/api/projects')).toEqual({ subscription_ids: [4242], address: null })
    expect(wrapper.props('open')).toBe(false)
    expect(useProjectsStore().list).toEqual([PROJECT])

    wrapper.unmount()
  })

  it('adds a project by its address', async () => {
    const backend = fakeBackend({ '/api/subscriptions': () => Response.json([]) })
    const wrapper = await openModal()

    expect(document.body.textContent).toContain('У этого аккаунта нет платных подписок.')
    await typeAddress('https://sponsr.ru/second/')
    buttonIn(document.body, 'Добавить и скачать').click()
    await flushPromises()

    expect(backend.bodyOf('/api/projects')).toEqual({
      subscription_ids: [],
      address: 'https://sponsr.ru/second/',
    })

    wrapper.unmount()
  })

  it('stays open and explains a refused address', async () => {
    fakeBackend({
      '/api/subscriptions': () => Response.json([]),
      '/api/projects': () => Response.json({ code: 'project_not_found' }, { status: 409 }),
    })
    const wrapper = await openModal()

    await typeAddress('nobody-home')
    buttonIn(document.body, 'Добавить и скачать').click()
    await flushPromises()

    expect(wrapper.props('open')).toBe(true)
    expect(document.body.textContent).toContain('На sponsr.ru нет проекта с таким адресом.')

    wrapper.unmount()
  })

  it('explains why the subscriptions are not shown, and still takes an address', async () => {
    fakeBackend({
      '/api/subscriptions': () => Response.json({ code: 'site_unavailable' }, { status: 502 }),
    })
    const wrapper = await openModal()

    expect(document.body.textContent).toContain('sponsr.ru не отвечает')
    expect(document.body.querySelector('input[type="text"]')).not.toBeNull()

    wrapper.unmount()
  })
})
