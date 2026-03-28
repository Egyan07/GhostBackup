import { Component } from "react";

export default class ErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { error: null };
  }

  static getDerivedStateFromError(error) {
    return { error };
  }

  componentDidCatch(error, info) {
    console.error("[ErrorBoundary] Uncaught render error:", error, info);
  }

  render() {
    if (this.state.error) {
      return (
        <div style={{
          display: "flex", flexDirection: "column", alignItems: "center",
          justifyContent: "center", height: "100vh",
          background: "var(--bg-base)", color: "var(--text-primary)",
          fontFamily: "var(--font-sans)", gap: 16, padding: 32,
        }}>
          <div style={{ fontSize: 32 }}>✖</div>
          <div style={{ fontSize: 16, fontWeight: 700 }}>Something went wrong</div>
          <div style={{ fontSize: 13, color: "var(--text-secondary)", textAlign: "center", maxWidth: 420 }}>
            {this.state.error.message}
          </div>
          <button
            className="btn btn-secondary btn-sm"
            onClick={() => this.setState({ error: null })}
          >
            Try Again
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}
