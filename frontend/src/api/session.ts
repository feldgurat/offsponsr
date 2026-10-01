import { api, ApiError } from './client'

/**
 * Trades the one-time launch token from the window URL for a session cookie.
 *
 * The token is dropped from the URL first, so it stays out of the router and the history.
 */
export async function openSession(): Promise<void> {
  const url = new URL(window.location.href)
  const token = url.searchParams.get('token')
  if (token === null) {
    return
  }

  url.searchParams.delete('token')
  window.history.replaceState(window.history.state, '', url)

  try {
    await api.post('/session', { token })
  } catch (error) {
    // A spent token is fine if the cookie from the first load is still there;
    // the next API call shows whether it is.
    if (!(error instanceof ApiError && error.status === 403)) {
      throw error
    }
  }
}
