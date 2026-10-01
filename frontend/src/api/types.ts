export interface AppInfo {
  name: string
  version: string
}

export interface LibraryInfo {
  id: string
  path: string
}

/** A library folder that couldn't be created or opened, and the reason as an error code. */
export interface LibraryFailure {
  path: string
  code: string
}

export interface LibraryStatus {
  library: LibraryInfo | null
  /** Set when the library from the previous run couldn't be reopened. */
  last_failure: LibraryFailure | null
}

export interface FolderChoice {
  /** null if the user cancelled the dialog. */
  path: string | null
}

export interface AccountInfo {
  signed_in: boolean
  email: string | null
  /** The stored session stopped working; the user has to sign in again. */
  expired: boolean
}

export interface ProjectInfo {
  id: number
  url: string
  title: string
  added_via: 'subscription' | 'url'
  sync_enabled: boolean
  last_synced_at: string | null
  /** Posts in the library, the ones deleted on the site included. */
  posts: number
  /** Readable posts whose whole text hasn't been downloaded yet. */
  posts_without_text: number
  posts_deleted: number
}

export interface SubscriptionInfo {
  id: number
  url: string
  title: string
  owner_name: string | null
  level_name: string | null
  in_library: boolean
}

export interface RunningSync {
  project_id: number
  title: string
  posts_done: number
  /** null until the site has told how many posts there are. */
  posts_total: number | null
}

export interface SyncFailure {
  project_id: number
  title: string
  code: string
}

export interface SyncInfo {
  running: RunningSync | null
  /** Ids of the projects waiting for their turn. */
  queue: number[]
  failures: SyncFailure[]
  cancelling: boolean
}

/** What the backend pushes over /api/events. */
export type ServerEvent = { type: 'sync'; state: SyncInfo } | { type: 'projects' }
