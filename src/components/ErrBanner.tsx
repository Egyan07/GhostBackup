interface ErrBannerError {
  message?: string;
  code?: string | null;
  fix?: string | null;
}

interface ErrBannerProps {
  error?: ErrBannerError | string | null;
  onDismiss?: () => void;
}

export default function ErrBanner({ error, onDismiss }: ErrBannerProps) {
  if (!error) return null;

  const message = typeof error === "string" ? error : error?.message || String(error);
  const code = typeof error === "string" ? null : (error?.code ?? null);
  const fix = typeof error === "string" ? null : (error?.fix ?? null);

  if (!message) return null;

  return (
    <div className="alert alert-error mb-12 flex justify-between items-center">
      <div className="flex items-center gap-8">
        <span className="alert-icon">⚠</span>
        <div>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            {code && (
              <span
                style={{
                  fontFamily: "var(--font-mono)",
                  fontSize: 11,
                  fontWeight: 700,
                  background: "rgba(248,113,113,0.15)",
                  padding: "1px 6px",
                  borderRadius: 4,
                  flexShrink: 0,
                }}
              >
                {code}
              </span>
            )}
            <span>{message}</span>
          </div>
          {fix && (
            <div style={{ fontSize: 12, color: "var(--text-secondary)", marginTop: 3 }}>
              Fix: {fix}
            </div>
          )}
        </div>
      </div>
      {onDismiss && (
        <button onClick={onDismiss} className="btn btn-ghost btn-sm" style={{ padding: "2px 8px" }}>
          ×
        </button>
      )}
    </div>
  );
}
