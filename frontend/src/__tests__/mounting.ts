import { createMemoryHistory, type Router } from 'vue-router'

import { i18n } from '@/i18n'
import { createAppRouter } from '@/router'

/** The app's own router over a history that lives in memory, as the tests have no address bar. */
export function testRouter(): Router {
  return createAppRouter(createMemoryHistory())
}

/** What a component needs around it to be mounted: the translations and a router. */
export function withPlugins(router: Router = testRouter()) {
  return { global: { plugins: [i18n, router] } }
}

/** A router that has already arrived at `path`. */
export async function routerAt(path: string): Promise<Router> {
  const router = testRouter()
  await router.push(path)
  await router.isReady()
  return router
}

export function buttonIn(root: ParentNode, label: string): HTMLButtonElement {
  const found = [...root.querySelectorAll('button')].find(
    (candidate) => candidate.textContent?.trim() === label,
  )
  if (!found) {
    throw new Error(`No button labelled "${label}"`)
  }
  return found
}
