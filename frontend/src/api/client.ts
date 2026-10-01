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

function withBody(method: string, body: unknown): RequestInit {
  return {
    method,
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  }
}

export type QueryValue = string | number | boolean | null | undefined

/** `/path?a=1&b=x` out of a path and parameters; the empty ones are left out. */
export function withQuery(path: string, params: Record<string, QueryValue>): string {
  const query = new URLSearchParams()
  for (const [name, value] of Object.entries(params)) {
    if (value !== null && value !== undefined && value !== '') {
      query.set(name, String(value))
    }
  }
  const text = query.toString()
  return text ? `${path}?${text}` : path
}

export const api = {
  get<T>(path: string, params?: Record<string, QueryValue>): Promise<T> {
    return request<T>(params ? withQuery(path, params) : path)
  },

  patch<T>(path: string, body: unknown): Promise<T> {
    return request<T>(path, withBody('PATCH', body))
  },

  delete<T = void>(path: string): Promise<T> {
    return request<T>(path, { method: 'DELETE' })
  },

  post<T = void>(path: string, body?: unknown): Promise<T> {
    if (body === undefined) {
      return request<T>(path, { method: 'POST' })
    }
    return request<T>(path, withBody('POST', body))
  },
}
