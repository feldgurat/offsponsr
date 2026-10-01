import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'

import { fakeBackend, SIGNED_IN, SIGNED_OUT } from '@/__tests__/backend'
import AccountMenu from '@/components/AccountMenu.vue'
import AccountNotice from '@/components/AccountNotice.vue'
import CookieLoginModal from '@/components/CookieLoginModal.vue'
import { i18n } from '@/i18n'
import { useAccountStore } from '@/stores/account'

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

beforeEach(() => {
  setActivePinia(createPinia())
})

afterEach(() => {
  document.body.innerHTML = ''
})

describe('AccountMenu', () => {
  it('offers to sign in when signed out', async () => {
    const backend = fakeBackend({ '/api/account/login': () => Response.json(SIGNED_IN) })
    const wrapper = mount(AccountMenu, plugins)

    expect(wrapper.text()).toContain('Войти по cookie')
    buttonIn(wrapper.element, 'Войти').click()
    await flushPromises()

    expect(backend.requests()).toEqual(['/api/account/login'])
    expect(wrapper.text()).toContain('reader@example.com')
    expect(wrapper.text()).toContain('Выйти')
  })

  it('signs out', async () => {
    const backend = fakeBackend({ '/api/account/logout': () => Response.json(SIGNED_OUT) })
    useAccountStore().info = SIGNED_IN
    const wrapper = mount(AccountMenu, plugins)

    buttonIn(wrapper.element, 'Выйти').click()
    await flushPromises()

    expect(backend.requests()).toEqual(['/api/account/logout'])
    expect(wrapper.text()).not.toContain('reader@example.com')
  })

  it('points at the login window while it is open', async () => {
    useAccountStore().busy = true

    const wrapper = mount(AccountMenu, plugins)

    expect(wrapper.text()).toContain('Войдите в открывшемся окне sponsr.ru')
    expect(wrapper.text()).not.toContain('Войти по cookie')
  })
})

describe('CookieLoginModal', () => {
  async function openModal() {
    const wrapper = mount(CookieLoginModal, {
      ...plugins,
      props: { open: true, 'onUpdate:open': (open: boolean) => wrapper.setProps({ open }) },
      attachTo: document.body,
    })
    await flushPromises()
    return wrapper
  }

  async function type(text: string) {
    const textarea = document.body.querySelector('textarea')!
    textarea.value = text
    textarea.dispatchEvent(new Event('input'))
    await flushPromises()
  }

  it('explains where to get the cookie string', async () => {
    const wrapper = await openModal()

    expect(document.body.textContent).toContain('Вход по строке Cookie')
    expect(document.body.querySelectorAll('ol li')).toHaveLength(4)
    expect(buttonIn(document.body, 'Войти').disabled).toBe(true)

    wrapper.unmount()
  })

  it('signs in and closes', async () => {
    const backend = fakeBackend({ '/api/account/login/cookie': () => Response.json(SIGNED_IN) })
    const wrapper = await openModal()

    await type('sid=good')
    buttonIn(document.body, 'Войти').click()
    await flushPromises()

    expect(backend.bodyOf('/api/account/login/cookie')).toEqual({ cookie: 'sid=good' })
    expect(useAccountStore().info).toEqual(SIGNED_IN)
    expect(wrapper.props('open')).toBe(false)

    wrapper.unmount()
  })

  it('stays open and explains when the site rejects the cookies', async () => {
    fakeBackend({
      '/api/account/login/cookie': () => Response.json({ code: 'invalid_cookie' }, { status: 422 }),
    })
    const wrapper = await openModal()

    await type('sid=stale')
    buttonIn(document.body, 'Войти').click()
    await flushPromises()

    expect(wrapper.props('open')).toBe(true)
    expect(document.body.textContent).toContain('sponsr.ru не принимает эти cookie')

    wrapper.unmount()
  })
})

describe('AccountNotice', () => {
  it('is silent when all is well', () => {
    expect(mount(AccountNotice, plugins).text()).toBe('')
  })

  it('says when the session has expired', () => {
    useAccountStore().info = { signed_in: false, email: null, expired: true }

    expect(mount(AccountNotice, plugins).text()).toContain('Сессия sponsr.ru истекла')
  })

  it('explains a failed sign-in', () => {
    useAccountStore().failure = 'site_unavailable'

    expect(mount(AccountNotice, plugins).text()).toContain('Не удалось связаться с sponsr.ru')
  })

  it('leaves a rejected cookie string to the dialog that asked for it', () => {
    useAccountStore().failure = 'invalid_cookie'

    expect(mount(AccountNotice, plugins).text()).toBe('')
  })
})
