export interface QueueProgress {
  login_total: number
  login_done: number
  receive_total: number
  receive_done: number
  login_busy_email: string
  receive_busy_email: string
  pending_login_emails: string[]
  pending_receive_emails: string[]
  pending_body_keys: string[]
  percent: number
}

export interface GroupDefinition {
  name: string
  color: string
  priority: number
}

export interface TagDefinition {
  name: string
  color: string
  priority: number
}

export interface AccountIssue {
  email: string
  status: string
  last_error_summary: string
  last_error: string
}

export interface Overview {
  total_accounts: number
  success_accounts: number
  failed_accounts: number
  processing_accounts: number
  cached_mails: number
  unread_mails: number
  queue: QueueProgress
}

export interface MailAccountSummary {
  index: number
  email: string
  group_name: string
  tags: string[]
  note: string
  status: string
  last_check: string
  unseen_count: number
  last_error: string
  last_error_summary: string
  auth_method: string
  flag_color: string
  mail_count: number
}

export interface MailItem {
  account_email: string
  folder: string
  local_key: string
  source: string
  subject: string
  from_text: string
  date_text: string
  date_value: string
  is_unread: boolean
  is_starred: boolean
  has_body: boolean
  body_text: string
}

export interface BodyTask {
  state: 'idle' | 'queued' | 'downloading' | 'done' | 'error'
  downloaded: number
  total: number
  speed_kb_s: number
  status: string
  size: number
  duration: number
}

export interface DashboardState {
  overview: Overview
  accounts: MailAccountSummary[]
  mails: MailItem[]
  settings: AppSettings
}

export interface AppSettings {
  auto_receive_interval: number
  import_delimiters: string[]
  txt_comment_prefix: string
  txt_skip_first_line: boolean
  startup_auto_login: boolean
  mail_list_limit: number
  mark_read_on_open: boolean
  custom_groups: GroupDefinition[]
  custom_tags: TagDefinition[]
  auto_receive_enabled: boolean
  auto_receive_interval_minutes: number
  token_refresh_enabled: boolean
  token_refresh_interval_minutes: number
  backup_enabled: boolean
  backup_interval_minutes: number
  backup_directory: string
  backup_keep_count: number
  oauth_client_id: string
  oauth_redirect_uri: string
  telegram_enabled: boolean
  telegram_bot_token: string
  telegram_chat_id: string
  telegram_mail_mode: 'off' | 'instant' | 'hourly'
  telegram_mail_group: string
  telegram_mail_summary_minutes: number
  telegram_notify_backup: boolean
}

export interface AuthUser {
  email: string
  role: string
}

export interface HeaderMetric {
  key?: 'success' | 'queue'
  icon: string
  label: string
  value: string | number
  clickable?: boolean
}
