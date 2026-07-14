import { sentenceCase } from "../utils/format";

interface StatusChipProps {
  status: string | boolean | null | undefined;
}

export function StatusChip({ status }: StatusChipProps) {
  const normalized = normalizeStatus(status);
  return (
    <span className={`status-chip status-${normalized.tone}`}>{normalized.label}</span>
  );
}

function normalizeStatus(status: string | boolean | null | undefined) {
  if (typeof status === "boolean") {
    return status
      ? { label: "Enabled", tone: "green" }
      : { label: "Disabled", tone: "neutral" };
  }

  const value = (status ?? "unknown").toLowerCase();
  if (
    ["healthy", "success", "succeeded", "completed", "active", "enabled"].includes(
      value,
    )
  ) {
    return { label: sentenceCase(value), tone: "green" };
  }
  if (["pending", "retryable", "draft", "degraded", "in_progress"].includes(value)) {
    return { label: sentenceCase(value), tone: "amber" };
  }
  if (
    ["failed", "error", "denied", "unavailable", "disabled", "cancelled"].includes(
      value,
    )
  ) {
    return { label: sentenceCase(value), tone: "red" };
  }
  return { label: sentenceCase(value), tone: "neutral" };
}
