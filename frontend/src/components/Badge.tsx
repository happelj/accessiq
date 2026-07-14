interface BadgeProps {
  children: React.ReactNode;
  tone?: "neutral" | "blue" | "green" | "amber" | "red";
}

export function Badge({ children, tone = "neutral" }: BadgeProps) {
  return <span className={`badge badge-${tone}`}>{children}</span>;
}
