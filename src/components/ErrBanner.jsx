export default function ErrBanner({ error, onDismiss }) {
  if (!error) return null;
  return (
    <div className="alert alert-error mb-12 flex justify-between items-center">
      <div className="flex items-center gap-8">
        <span className="alert-icon">⚠</span>
        <span>{error}</span>
      </div>
      {onDismiss && (
        <button onClick={onDismiss} className="btn btn-ghost btn-sm" style={{ padding: "2px 8px" }}>×</button>
      )}
    </div>
  );
}
