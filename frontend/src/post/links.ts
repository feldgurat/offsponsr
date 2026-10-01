const SITE = 'https://sponsr.ru/'
const SITE_HOSTS = new Set(['sponsr.ru', 'www.sponsr.ru'])

/** Players of other sites that are shown right in a post while the computer is online. */
const EMBED_HOSTS = new Set([
  'www.youtube.com',
  'youtube.com',
  'www.youtube-nocookie.com',
  'youtube-nocookie.com',
  'rutube.ru',
  'vk.com',
  'vk.ru',
  'vkvideo.ru',
  't.me',
])

/** The full address a link in a post leads to; links without a host belong to sponsr.ru. */
export function absoluteLink(href: string): string | null {
  try {
    const url = new URL(href, SITE)
    return ['http:', 'https:', 'mailto:'].includes(url.protocol) ? url.href : null
  } catch {
    return null
  }
}

/** The address of a picture in a post, to load it from the web; one without a host belongs to the site. */
export function pictureAddress(src: string): string | null {
  if (src.startsWith('data:image/')) {
    // A picture written into the text itself.
    return src
  }
  try {
    const url = new URL(src, SITE)
    return url.protocol === 'https:' || url.protocol === 'http:' ? url.href : null
  } catch {
    return null
  }
}

/** The id of the post a link leads to, if it is a link to a post on sponsr.ru. */
export function linkedPostId(href: string): number | null {
  try {
    const url = new URL(href, SITE)
    if (!SITE_HOSTS.has(url.hostname)) {
      return null
    }
    // sponsr.ru/<project>/<post id>/<anything>
    const match = /^\/[^/]+\/(\d+)(?:\/|$)/.exec(url.pathname)
    return match ? Number(match[1]) : null
  } catch {
    return null
  }
}

/** The address to frame, if the frame is a player the app shows; null for anything else. */
export function embedAddress(src: string): string | null {
  try {
    const url = new URL(src, SITE)
    return url.protocol === 'https:' && EMBED_HOSTS.has(url.hostname) ? url.href : null
  } catch {
    return null
  }
}
