import { formatNumber } from "../utils/format";

interface StatCardProps {
  label: string;
  value: number | string;
  detail?: string;
}

export function StatCard({ label, value, detail }: StatCardProps) {
  return (
    <section className="stat-card">
      <span>{label}</span>
      <strong>{typeof value === "number" ? formatNumber(value) : value}</strong>
      {detail ? <small>{detail}</small> : null}
    </section>
  );
}
