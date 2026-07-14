import { Component, type ErrorInfo, type ReactNode } from "react";
import { ErrorPanel } from "./ErrorPanel";

interface ErrorBoundaryProps {
  children: ReactNode;
}

interface ErrorBoundaryState {
  error: Error | null;
}

export class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  state: ErrorBoundaryState = { error: null };

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { error };
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo): void {
    console.error("AccessIQ UI error", error, errorInfo);
  }

  render() {
    if (this.state.error) {
      return (
        <main className="standalone-page">
          <ErrorPanel
            title="The interface could not render"
            message={this.state.error.message}
          />
        </main>
      );
    }

    return this.props.children;
  }
}
