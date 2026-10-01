export class ApiError extends Error {
  constructor(
    readonly status: number,
    path: string,
    /** What went wrong, in the backend's terms; the UI has a message for each code. */
    readonly code: string | null = null,
  ) {
    super(`API ${path} responded with ${status}`)
    this.name = 'ApiError'
  }
}

async function errorCode(response: Response): Promise<string | null> {
  try {
    const body: unknown = await response.json()
    if (typeof body === 'object' && body !== null && 'code' in body) {
      return typeof body.code === 'string' ? body.code : null
    }
  } catch {
    // Not every error comes with a JSON body.
  }
  return null
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/api${path}`, init)
  if (!response.ok) {
    throw new ApiError(response.status, path, await errorCode(response))
  }
  if (response.status === 204) {
    return undefined as T
  }
  return (await response.json()) as T
}

export const api = {
  get<T>(path: string): Promise<T> {
    return request<T>(path)
  },

  post<T = void>(path: string, body?: unknown): Promise<T> {
    if (body === undefined) {
      return request<T>(path, { method: 'POST' })
    }
    return request<T>(path, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })
  },
}
