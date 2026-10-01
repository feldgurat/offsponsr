import type { MediaInfo } from '@/api/types'

import { sanitizePost } from './sanitize'

/** The site marks the place of an audio player in a text with an empty block carrying the file's id. */
export const AUDIO_PLACE = 'div.post-podcast[data-id]'

/** Classes of the site's markup that mean something to the way the app shows a text. */
export const KEPT_CLASSES = new Set(['paragraph-without-indent', 'post-video', 'post-image'])

/** The audio files that have a place of their own inside the text, by the ids of their rows. */
export function audioPlacedInText(html: string | null, media: MediaInfo[]): Set<number> {
  const placed = new Set<number>()
  if (!html) {
    return placed
  }
  const audio = new Map(
    media.filter((item) => item.kind === 'audio').map((item) => [item.source_id, item.id]),
  )
  for (const place of sanitizePost(html).querySelectorAll(AUDIO_PLACE)) {
    const id = audio.get(place.getAttribute('data-id'))
    if (id !== undefined) {
      placed.add(id)
    }
  }
  return placed
}
