import { createRouter, createWebHistory, type Router, type RouterHistory } from 'vue-router'

import LibraryView from '@/views/LibraryView.vue'
import PostView from '@/views/PostView.vue'
import ProjectView from '@/views/ProjectView.vue'
import SettingsView from '@/views/SettingsView.vue'
import SyncView from '@/views/SyncView.vue'

/** How long going back waits for the page to be drawn before scrolling to where it was left. */
const RESTORE_DELAY = 50

/**
 * A factory, not a module-level instance: the history reads the window URL when it is created,
 * and that has to happen after the launch token is dropped from it.
 */
export function createAppRouter(history: RouterHistory = createWebHistory()): Router {
  return createRouter({
    history,
    routes: [
      { path: '/', name: 'library', component: LibraryView },
      { path: '/projects/:id(\\d+)', name: 'project', component: ProjectView },
      { path: '/posts/:id(\\d+)', name: 'post', component: PostView },
      { path: '/sync', name: 'sync', component: SyncView },
      { path: '/settings', name: 'settings', component: SettingsView },
      { path: '/:rest(.*)*', redirect: { name: 'library' } },
    ],
    scrollBehavior(to, from, savedPosition) {
      if (savedPosition) {
        // Going back: the feed is still on hand (see the feed store), so it is there after a tick.
        return new Promise((resolve) => {
          setTimeout(() => resolve(savedPosition), RESTORE_DELAY)
        })
      }
      // Filters and «показать ещё» change the address of the same page: stay where you are.
      return to.path === from.path ? false : { top: 0 }
    },
  })
}
