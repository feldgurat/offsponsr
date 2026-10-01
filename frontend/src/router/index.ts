import { createRouter, createWebHistory, type Router } from 'vue-router'

import LibraryView from '@/views/LibraryView.vue'

/**
 * A factory, not a module-level instance: the history reads the window URL when it is created,
 * and that has to happen after the launch token is dropped from it.
 */
export function createAppRouter(): Router {
  return createRouter({
    history: createWebHistory(),
    routes: [
      {
        path: '/',
        name: 'library',
        component: LibraryView,
      },
    ],
  })
}
