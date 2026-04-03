/* ─── API Response Types ──────────────────────────────────────────────────── */

export interface RunSummary {
  id: number;
  status: string;
  started_at: string;
  files_transferred: number;
  files_failed?: number;
  duration_seconds?: number;
  duration_human?: string;
  bytes_human?: string;
  total_size_gb?: number;
  folder_summary?: Record<string, FolderStatus>;
  library_summary?: Record<string, FolderStatus>;
}

export interface FolderStatus {
  status?: string;
  files_transferred: number;
  files_failed?: number;
  size_gb?: number;
  pct?: number;
}

export interface DashboardData {
  runs: RunSummary[];
  last_run: RunSummary | null;
  active_run: ActiveRun | null;
  ssd_storage: SsdStorage;
  schedule: ScheduleInfo;
  next_run: string | null;
}

export interface ActiveRun {
  status: string;
  overall_pct: number;
  files_transferred: number;
  files_failed?: number;
}

export interface SsdStorage {
  status: string;
  used_gb: number;
  total_gb: number;
  available_gb?: number;
  path?: string;
  error?: string;
  fs_type?: string;
}

export interface ScheduleInfo {
  label?: string;
  time?: string;
  timezone?: string;
}

export interface HealthData {
  status?: string;
  scheduler_running?: boolean;
  next_run?: string;
  key_storage?: string;
}

export interface RunStatus {
  status: string;
  overall_pct: number;
  files_transferred: number;
  files_failed: number;
  bytes_transferred?: number;
  started_at?: string;
  feed: FeedItem[];
  libraries: Record<string, { pct: number }>;
}

export interface FeedItem {
  time: string;
  file: string;
  size_mb: number;
  library: string;
}

export interface LogEntry {
  logged_at: string;
  level: string;
  message: string;
}

export interface BackupConfig {
  ssd_path?: string;
  encryption_active?: boolean;
  hkdf_salt_active?: boolean;
  schedule?: { time?: string; timezone?: string };
  performance?: { concurrency?: number; max_file_size_gb?: number };
  backup?: { verify_checksums?: boolean; exclude_patterns?: string[] };
  sources?: SourceFolder[];
  sites?: SourceFolder[];
  smtp?: SmtpConfig;
  retention?: RetentionConfig;
}

export interface SourceFolder {
  label?: string;
  name?: string;
  path: string;
  enabled?: boolean;
}

export interface SmtpConfig {
  host?: string;
  port?: number;
  user?: string;
  recipients?: string[];
}

export interface RetentionConfig {
  daily_days?: number;
  weekly_days?: number;
  compliance_years?: number;
  guard_days?: number;
}

export interface RestoreResult {
  dry_run: boolean;
  files_to_restore?: number;
  files_count?: number;
  files?: { name: string; size: number }[];
  destination: string;
}

export interface AlertData {
  alerts: Alert[];
  unread_count: number;
}

export interface Alert {
  id: number;
  level: string;
  title: string;
  body: string;
  ts?: string;
  run_id?: number;
  dismissed?: boolean;
}

export interface WatcherStatus {
  running: boolean;
  debounce_seconds?: number;
  cooldown_seconds?: number;
  sources?: WatcherSource[];
}

export interface WatcherSource {
  label: string;
  path: string;
  pending_changes?: number;
  last_triggered?: string;
}

export interface DrillStatus {
  last_completed: string | null;
  days_since_last: number | null;
  next_due: string | null;
  overdue: boolean;
  history?: unknown[];
}

export interface VerifyResult {
  verified: number;
  failed: number;
  missing: number;
}

/* ─── Nav Types ───────────────────────────────────────────────────────────── */

export interface NavItem {
  id: string;
  label: string;
  icon: string;
  sec: string;
}
