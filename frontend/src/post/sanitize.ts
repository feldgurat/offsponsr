import DOMPurify, { type Config } from 'dompurify'

/**
 * The text of a post is somebody else's HTML, and the window it is shown in can talk to the
 * app's own API. So before anything is shown the text is cut down to plain formatting:
 * no scripts, no event handlers, no forms, no styles, nothing that loads by itself.
 *
 * Player frames are let through as inert markers only: the renderer (PostBody) replaces each
 * with a component that decides what, if anything, may be loaded in its place.
 */
const OPTIONS: Config & { RETURN_DOM_FRAGMENT: true } = {
  ADD_TAGS: ['iframe'],
  ADD_ATTR: ['allowfullscreen'],
  FORBID_TAGS: [
    'style',
    'form',
    'input',
    'button',
    'textarea',
    'select',
    'option',
    'video',
    'audio',
    'source',
    'track',
    'object',
    'embed',
    'link',
    'meta',
    'base',
    'svg',
    'math',
  ],
  // `style` could lay a post over the app's own controls; `srcset` would load a picture from
  // the web behind the back of the local copy; `id` and `name` could shadow the page's own.
  FORBID_ATTR: ['style', 'srcset', 'sizes', 'id', 'name', 'contenteditable', 'loading'],
  RETURN_DOM_FRAGMENT: true,
}

export function sanitizePost(html: string): DocumentFragment {
  return DOMPurify.sanitize(html, OPTIONS)
}
