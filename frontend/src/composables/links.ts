import { useRouter } from 'vue-router'

import { api } from '@/api/client'
import { absoluteLink, linkedPostId } from '@/post/links'
import { useMediaStore } from '@/stores/media'

/** Where the links inside a post's text lead. */
export function useLinks() {
  const router = useRouter()
  const media = useMediaStore()

  /**
   * A link to a post the library has opens that post here; anything else opens in the user's
   * browser. The window itself never leaves the app.
   */
  async function follow(href: string): Promise<void> {
    const postId = linkedPostId(href)
    if (postId !== null) {
      try {
        await api.get(`/posts/${postId}`)
        await router.push({ name: 'post', params: { id: postId } })
        return
      } catch {
        // Not in the library: it is a link like any other.
      }
    }
    const url = absoluteLink(href)
    if (url !== null) {
      await media.openLink(url).catch(() => undefined)
    }
  }

  return { follow }
}
