import { describe, expect, it } from 'vitest'

import { media } from '@/__tests__/backend'
import { audioPlacedInText } from '@/post/content'
import { absoluteLink, embedAddress, linkedPostId, pictureAddress } from '@/post/links'
import { sanitizePost } from '@/post/sanitize'

function clean(html: string): string {
  const holder = document.createElement('div')
  holder.append(sanitizePost(html))
  return holder.innerHTML
}

describe('sanitizePost', () => {
  it('keeps plain formatting', () => {
    const html =
      '<h2>Заголовок</h2><p class="paragraph-without-indent">Текст <b>жирный</b> и <i>курсив</i>.</p>' +
      '<blockquote><p>Цитата</p></blockquote><ul><li>пункт</li></ul><a href="https://example.com">ссылка</a>'

    expect(clean(html)).toBe(html)
  })

  it('drops scripts and everything that runs by itself', () => {
    const html = clean(
      '<p onclick="alert(1)">Текст</p><script>alert(2)</script>' +
        '<img src="x" onerror="alert(3)"><a href="javascript:alert(4)">ссылка</a>' +
        '<svg onload="alert(5)"></svg><object data="x"></object><embed src="x">',
    )

    expect(html).not.toMatch(/alert|script|onerror|onclick|javascript|svg|object|embed/)
    expect(html).toContain('<p>Текст</p>')
    expect(html).toContain('<img src="x">')
  })

  it('drops styles, forms and names that could shadow the page', () => {
    const html = clean(
      '<p style="position:fixed;top:0" id="app" name="app">Текст</p><style>p { display: none }</style>' +
        '<form action="https://evil.example"><input name="password"><button>Отправить</button></form>',
    )

    // Of a form only its words are left, as plain text.
    expect(html).toBe('<p>Текст</p>Отправить')
  })

  it('never lets a picture load from a set of addresses behind the local copy', () => {
    expect(clean('<img src="a.webp" srcset="https://evil.example/b.webp 2x" sizes="100vw">')).toBe(
      '<img src="a.webp">',
    )
  })

  it('keeps frames as markers, with the labels the backend put on them', () => {
    const html = clean(
      '<iframe data-media="8" src="https://kinescope.io/abc" allowfullscreen="true"></iframe>' +
        '<img data-media="7" src="https://media.sponsr.ru/a.webp">' +
        '<div class="post-podcast" contenteditable="false" data-id="6001"></div>',
    )

    expect(html).toContain('<iframe data-media="8" src="https://kinescope.io/abc"')
    expect(html).toContain('<img data-media="7"')
    expect(html).toContain('<div class="post-podcast" data-id="6001"></div>')
  })

  it("drops the site's own audio and video tags: the app has players of its own", () => {
    expect(clean('<p>Текст</p><video src="x" autoplay></video><audio src="y"></audio>')).toBe(
      '<p>Текст</p>',
    )
  })
})

describe('links of a post', () => {
  it('makes addresses without a host belong to sponsr.ru', () => {
    expect(absoluteLink('/fictional-almanac/9001/')).toBe(
      'https://sponsr.ru/fictional-almanac/9001/',
    )
    expect(absoluteLink('https://example.com/a?b=1')).toBe('https://example.com/a?b=1')
    expect(absoluteLink('mailto:author@example.com')).toBe('mailto:author@example.com')
  })

  it('refuses addresses the system has no business opening', () => {
    expect(absoluteLink('javascript:alert(1)')).toBeNull()
    expect(absoluteLink('file:///C:/Windows/system32/calc.exe')).toBeNull()
    expect(absoluteLink('data:text/html,x')).toBeNull()
  })

  it('recognises a link to a post on sponsr.ru', () => {
    expect(linkedPostId('https://sponsr.ru/fictional-almanac/9001/slug')).toBe(9001)
    expect(linkedPostId('https://www.sponsr.ru/fictional-almanac/9001')).toBe(9001)
    expect(linkedPostId('/fictional-almanac/9001/')).toBe(9001)
    expect(linkedPostId('https://sponsr.ru/fictional-almanac/')).toBeNull()
    expect(linkedPostId('https://example.com/fictional-almanac/9001/')).toBeNull()
    expect(linkedPostId('https://sponsr.ru/9001/')).toBeNull()
  })

  it('frames only the players it knows, and only over https', () => {
    expect(embedAddress('https://www.youtube.com/embed/abc?rel=0')).toBe(
      'https://www.youtube.com/embed/abc?rel=0',
    )
    expect(embedAddress('https://rutube.ru/play/embed/1')).toBe('https://rutube.ru/play/embed/1')
    expect(embedAddress('https://vk.com/video_ext.php?oid=1')).toBe(
      'https://vk.com/video_ext.php?oid=1',
    )
    expect(embedAddress('http://www.youtube.com/embed/abc')).toBeNull()
    expect(embedAddress('https://player.example.org/embed/42')).toBeNull()
    expect(embedAddress('https://youtube.com.evil.example/embed/abc')).toBeNull()
    expect(embedAddress('javascript:alert(1)')).toBeNull()
    // The site's own player page is not somebody else's player.
    expect(embedAddress('/post/video/?video_id=1')).toBeNull()
  })

  it('gives a picture its address on the web', () => {
    expect(pictureAddress('https://media.sponsr.ru/a.webp?1')).toBe(
      'https://media.sponsr.ru/a.webp?1',
    )
    expect(pictureAddress('/images/a.webp')).toBe('https://sponsr.ru/images/a.webp')
    expect(pictureAddress('x')).toBe('https://sponsr.ru/x')
    expect(pictureAddress('data:image/png;base64,AAAA')).toBe('data:image/png;base64,AAAA')
    expect(pictureAddress('data:text/html,<script>1</script>')).toBeNull()
    expect(pictureAddress('javascript:alert(1)')).toBeNull()
  })
})

describe('audioPlacedInText', () => {
  const files = [
    media({ id: 5, kind: 'audio', source_id: '6001' }),
    media({ id: 6, kind: 'audio', source_id: '6002' }),
    media({ id: 7, kind: 'attach', source_id: '6003' }),
  ]

  it('finds the audio that has a place of its own in the text', () => {
    const html =
      '<p>До</p><div class="post-podcast" contenteditable="false" data-id="6001"></div><p>После</p>'

    expect([...audioPlacedInText(html, files)]).toEqual([5])
  })

  it('ignores places for files the post does not have, and files that are not audio', () => {
    const html =
      '<div class="post-podcast" data-id="7777"></div><div class="post-podcast" data-id="6003"></div>'

    expect(audioPlacedInText(html, files).size).toBe(0)
    expect(audioPlacedInText(null, files).size).toBe(0)
    expect(audioPlacedInText('<p>Текст</p>', files).size).toBe(0)
  })
})
