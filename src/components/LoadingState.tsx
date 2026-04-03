export default function LoadingState() {
  return (
    <div className="loading">
      <div style={{ fontSize: 20, marginBottom: 10, animation: "pulse-dot 1.2s ease-in-out infinite" }}>⟳</div>
      Loading…
    </div>
  );
}
