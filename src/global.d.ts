interface GhostBackupBridge {
  apiUrl(): Promise<string>;
  getApiToken(): Promise<string>;
  version(): Promise<string>;
  author(): Promise<string>;
  openDirectory(): Promise<string | null>;
  onBackendReady(cb: () => void): (() => void) | undefined;
  onBackendCrashed(cb: (data: { exitCode: number }) => void): (() => void) | undefined;
  onAlertNew(cb: () => void): (() => void) | undefined;
  backendStatus(): Promise<{ ready: boolean }>;
}

interface Window {
  ghostbackup?: Partial<GhostBackupBridge>;
}
