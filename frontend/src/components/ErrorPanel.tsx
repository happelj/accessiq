import { ApiError } from "../services/apiClient";

interface ErrorPanelProps {
  title?: string;
  message?: string;
  error?: unknown;
}

export function ErrorPanel({
  title = "Request failed",
  message,
  error,
}: ErrorPanelProps) {
  return (
    <div className="error-panel" role="alert">
      <strong>{title}</strong>
      <p>{message ?? describeError(error)}</p>
    </div>
  );
}

export function describeError(error: unknown): string {
  if (error instanceof ApiError) {
    return `${error.status}: ${error.message}`;
  }
  if (error instanceof Error) {
    return error.message;
  }
  return "Unexpected error";
}
