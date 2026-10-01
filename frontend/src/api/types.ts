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
