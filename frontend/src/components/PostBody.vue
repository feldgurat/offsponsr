<script lang="ts">
import { Image } from 'ant-design-vue'
import { computed, defineComponent, h, type PropType, ref, type VNodeChild } from 'vue'

import type { MediaInfo } from '@/api/types'
import { useLinks } from '@/composables/links'
import { AUDIO_PLACE, KEPT_CLASSES } from '@/post/content'
import { pictureAddress } from '@/post/links'
import { sanitizePost } from '@/post/sanitize'

import EmbedFrame from './EmbedFrame.vue'
import MediaAudio from './MediaAudio.vue'
import MediaVideo from './MediaVideo.vue'

/** Marks the links that came with the post, as opposed to the app's own controls put into the text. */
const POST_LINK = 'data-post-link'

/** Attributes the renderer sets itself or has no use for. */
const DROPPED = new Set(['class', 'target', 'rel', 'data-media', POST_LINK])

/**
 * The text of a post. The site's HTML is cleaned (see post/sanitize.ts) and then rebuilt
 * element by element, so that nothing of it reaches the page unseen:
 * pictures point at their copies in the library, the site's video frames become the app's
 * own player, frames of other sites become a guarded frame or a link, and links are
 * followed by the app instead of the window.
 */
export default defineComponent({
  name: 'PostBody',
  props: {
    html: { type: String, required: true },
    media: { type: Array as PropType<MediaInfo[]>, default: () => [] },
  },
  setup(props) {
    const links = useLinks()
    /** The picture opened in full size. */
    const preview = ref<string | null>(null)

    const fragment = computed(() => sanitizePost(props.html))
    const byId = computed(() => new Map(props.media.map((item) => [item.id, item])))
    const audioBySource = computed(
      () =>
        new Map(
          props.media.filter((item) => item.kind === 'audio').map((item) => [item.source_id, item]),
        ),
    )

    function labelled(element: Element): MediaInfo | undefined {
      const id = element.getAttribute('data-media')
      return id === null ? undefined : byId.value.get(Number(id))
    }

    function picture(element: Element, key: number): VNodeChild {
      // The copy in the library; until it is downloaded, the picture's address on the web.
      const original = element.getAttribute('src') ?? element.getAttribute('data-src')
      const src = labelled(element)?.url ?? (original ? pictureAddress(original) : null)
      if (!src) {
        return null
      }
      return h('img', {
        key,
        src,
        alt: element.getAttribute('alt') ?? '',
        loading: 'lazy',
        class: 'post-body__image',
        onClick: () => {
          preview.value = src
        },
      })
    }

    function frame(element: Element, key: number): VNodeChild {
      const media = labelled(element)
      if (media?.kind === 'video') {
        return h(MediaVideo, { key, media })
      }
      return h(EmbedFrame, { key, src: media?.source_url ?? element.getAttribute('src') ?? '' })
    }

    function render(node: Node, key: number): VNodeChild {
      if (node.nodeType === Node.TEXT_NODE) {
        return node.textContent
      }
      if (node.nodeType !== Node.ELEMENT_NODE) {
        return null
      }
      const element = node as Element
      const tag = element.tagName.toLowerCase()
      if (tag === 'img') {
        return picture(element, key)
      }
      if (tag === 'iframe') {
        return frame(element, key)
      }
      if (element.matches(AUDIO_PLACE)) {
        const audio = audioBySource.value.get(element.getAttribute('data-id'))
        return audio ? h(MediaAudio, { key, media: audio }) : null
      }

      const attributes: Record<string, unknown> = { key }
      for (const { name, value } of element.attributes) {
        // The cleaning has removed event handlers already; this makes sure none is ever set.
        if (!DROPPED.has(name) && !name.startsWith('on')) {
          attributes[name] = value
        }
      }
      const classes = [...element.classList].filter((name) => KEPT_CLASSES.has(name))
      if (classes.length) {
        attributes.class = classes
      }
      if (tag === 'a') {
        attributes[POST_LINK] = ''
      }
      return h(tag, attributes, children(element))
    }

    function children(parent: Node): VNodeChild[] {
      return [...parent.childNodes].map(render)
    }

    function onClick(event: MouseEvent): void {
      const anchor = (event.target as Element).closest('a')
      if (anchor === null) {
        return
      }
      // Whatever the link is, the window stays in the app.
      event.preventDefault()
      // A link of the app's own (in a control put into the text) has done its work by now.
      const href = anchor.hasAttribute(POST_LINK) ? anchor.getAttribute('href') : null
      if (href) {
        void links.follow(href)
      }
    }

    return () =>
      // `auxclick` is the middle button, which would otherwise open the link in a new window.
      h('div', { class: 'post-body', onClick, onAuxclick: onClick }, [
        ...children(fragment.value),
        preview.value === null
          ? null
          : h(Image, {
              key: 'preview',
              style: { display: 'none' },
              src: preview.value,
              preview: {
                visible: true,
                onVisibleChange: (visible: boolean) => {
                  if (!visible) {
                    preview.value = null
                  }
                },
              },
            }),
      ])
  },
})
</script>

<style>
/* Not scoped: the elements are the post's own, built in the render function above. */
.post-body {
  font-size: 16px;
  line-height: 1.6;
  overflow-wrap: anywhere;
}

.post-body p {
  margin: 0 0 1em;
}

.post-body h1,
.post-body h2,
.post-body h3,
.post-body h4 {
  margin: 1.4em 0 0.6em;
  font-weight: 500;
  line-height: 1.3;
}

.post-body h1 {
  font-size: 24px;
}

.post-body h2 {
  font-size: 22px;
}

.post-body h3 {
  font-size: 19px;
}

.post-body a {
  color: var(--c-primary, #fa541c);
  cursor: pointer;
}

.post-body a:hover {
  text-decoration: underline;
}

.post-body blockquote {
  margin: 0 0 1em;
  padding: 4px 16px;
  border-left: 3px solid var(--c-primary, #fa541c);
  background: var(--c-fill, rgba(128, 128, 128, 0.08));
}

.post-body blockquote > :last-child {
  margin-bottom: 0;
}

.post-body ul,
.post-body ol {
  margin: 0 0 1em;
  padding-left: 1.5em;
}

.post-body table {
  display: block;
  max-width: 100%;
  margin: 0 0 1em;
  overflow-x: auto;
  border-collapse: collapse;
}

.post-body td,
.post-body th {
  padding: 6px 10px;
  border: 1px solid var(--c-border, rgba(128, 128, 128, 0.25));
}

.post-body pre {
  padding: 12px;
  overflow-x: auto;
  border-radius: 8px;
  background: var(--c-fill, rgba(128, 128, 128, 0.08));
}

.post-body hr {
  margin: 1.5em 0;
  border: 0;
  border-top: 1px solid var(--c-border, rgba(128, 128, 128, 0.25));
}

.post-body__image {
  display: block;
  max-width: 100%;
  height: auto;
  margin: 12px auto;
  border-radius: 4px;
  cursor: zoom-in;
}
</style>
