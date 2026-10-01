import { vi } from 'vitest'

// jsdom lays nothing out, so there is nowhere to scroll; the router asks for it all the same.
vi.stubGlobal('scrollTo', vi.fn())
// This file is checked without the DOM's types, hence the roundabout way to an element's prototype.
const element = (globalThis as unknown as { Element: { prototype: Record<string, unknown> } })
  .Element
element.prototype.scrollIntoView = vi.fn()

// jsdom has no matchMedia; the theme store and Ant Design Vue both call it.
vi.stubGlobal(
  'matchMedia',
  vi.fn((query: string) => ({
    matches: false,
    media: query,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    addListener: vi.fn(),
    removeListener: vi.fn(),
    dispatchEvent: vi.fn(),
    onchange: null,
  })),
)
