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
  intent: string | null
  /** Addresses of the pictures: the copies in the library once they are downloaded. */
  logo: string | null
  cover: string | null
  added_via: 'subscription' | 'url'
  sync_enabled: boolean
  media_mode_audio: MediaMode
  media_mode_video: MediaMode
  media_mode_attach: MediaMode
  video_quality: VideoQuality
  last_synced_at: string | null
  /** Posts in the library, the ones deleted on the site included. */
  posts: number
  /** Readable posts whose whole text hasn't been downloaded yet. */
  posts_without_text: number
  posts_deleted: number
  /** Posts the account can't read. */
  posts_closed: number
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

export interface ActiveDownload {
  key: string
  title: string
  bytes_done: number
  /** null while the size is not known. */
  bytes_total: number | null
}

export interface DownloadsInfo {
  active: ActiveDownload[]
  queued: number
  /** Since the queue last started from empty. */
  done: number
  failed: number
  cancelling: boolean
}

/** What the backend pushes over /api/events. */
export type ServerEvent =
  | { type: 'sync'; state: SyncInfo }
  | { type: 'downloads'; state: DownloadsInfo }
  | { type: 'projects' }
  /** A download is through (done, failed or cancelled): `id` is of a media row, a post or a project. */
  | { type: 'file'; kind: 'media' | 'post_cover' | 'project_logo' | 'project_cover'; id: number }

export type MediaMode = 'auto' | 'manual'

/** The tallest video to download, in pixels; null is the best there is. */
export type VideoQuality = 1080 | 720 | 480 | 360 | null

export interface ProjectSettings {
  sync_enabled?: boolean
  media_mode_audio?: MediaMode
  media_mode_video?: MediaMode
  media_mode_attach?: MediaMode
  video_quality?: VideoQuality
}

/** Known files of the kinds just switched to «сразу» that are not in the library yet. */
export interface PendingMedia {
  files: number
  /** The sizes that are known, added up; videos don't tell theirs in advance. */
  bytes: number
  files_without_size: number
}

export interface ProjectUpdate {
  project: ProjectInfo
  to_download: PendingMedia
}

export interface LevelInfo {
  id: number
  name: string
  /** Roubles a month. */
  price: number | null
}

export interface TagInfo {
  id: number
  name: string
}

export type MediaKind = 'image' | 'audio' | 'video' | 'attach' | 'embed'
export type MediaState = 'pending' | 'queued' | 'downloading' | 'done' | 'error' | 'skipped'

export interface MediaInfo {
  id: number
  kind: MediaKind
  source_id: string | null
  /** Where it lives on the web: the address of a picture or of a player frame. */
  source_url: string | null
  title: string | null
  size: number | null
  /** Seconds. */
  duration: number | null
  state: MediaState
  /** The code of what went wrong, if the download failed. */
  error: string | null
  /** Where to load the file from once it is in the library; never set for attachments. */
  url: string | null
  file_name: string | null
  /** Whether the downloaded file is a document or media the system may be asked to open. */
  can_open: boolean
}

export type PostStatus = 'active' | 'deleted_on_site' | 'unavailable'

/** A post as the feeds show it. */
export interface PostCard {
  id: number
  project_id: number
  title: string
  date: string
  /** The beginning of the text without markup. */
  excerpt: string
  cover: string | null
  /** The account can't read it and the library has no text of it. */
  closed: boolean
  status: PostStatus
  /** False while the library has only the beginning of the text. */
  text_is_full: boolean
  level: LevelInfo | null
  /** Seconds. */
  duration_text: number | null
  duration_audio: number | null
  duration_video: number | null
  has_audio: boolean
  has_video: boolean
  pinned: boolean
  tags: TagInfo[]
  /** The text with its pictures and players labelled with `data-media`; only where asked for. */
  html: string | null
  media: MediaInfo[]
}

export interface FeedPage {
  total: number
  page: number
  per_page: number
  posts: PostCard[]
}

export interface PostLink {
  id: number
  title: string
}

export interface PostDetails extends PostCard {
  project: { id: number; url: string; title: string }
  newer: PostLink | null
  older: PostLink | null
}

export type ThemeMode = 'light' | 'dark' | 'system'
export type FeedView = 'stream' | 'feed' | 'tile' | 'list'

export interface Settings {
  theme: ThemeMode
  feed_view: FeedView
  hide_closed: boolean
}

export interface SyncRun {
  id: number
  project_id: number | null
  title: string | null
  started_at: string
  finished_at: string | null
  outcome: 'ok' | 'cancelled' | 'failed' | 'unfinished'
  /** Whether the whole list of posts was read, not just its beginning. */
  full: boolean
  posts_new: number
  posts_changed: number
  posts_deleted: number
}

export interface FailedDownload {
  media_id: number
  kind: MediaKind
  title: string | null
  error: string | null
  post_id: number
  post_title: string
  project_id: number
}

export interface FailedDownloads {
  total: number
  items: FailedDownload[]
}

export interface FfmpegInfo {
  found: boolean
  path: string | null
}
