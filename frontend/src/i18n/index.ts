import { createI18n } from 'vue-i18n'

import ru from './locales/ru'

/**
 * Russian plural forms. Messages list them as `none | one | few | many`
 * (0 постов | 1 пост | 2 поста | 5 постов); with three forms the first is left out.
 */
export function russianPlural(choice: number, choicesLength: number): number {
  const offset = choicesLength === 4 ? 1 : 0
  if (choice === 0 && choicesLength === 4) {
    return 0
  }
  const lastTwo = Math.abs(choice) % 100
  const last = lastTwo % 10
  if (lastTwo > 10 && lastTwo < 20) {
    return 2 + offset
  }
  if (last === 1) {
    return offset
  }
  if (last >= 2 && last <= 4) {
    return 1 + offset
  }
  return 2 + offset
}

export const i18n = createI18n({
  legacy: false,
  locale: 'ru',
  fallbackLocale: 'ru',
  pluralRules: { ru: russianPlural },
  messages: { ru },
})
