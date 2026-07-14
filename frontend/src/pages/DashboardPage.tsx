import { useQuery } from "@tanstack/react-query";
import { Card } from "../components/Card";
import { DataTable } from "../components/DataTable";
import { ErrorPanel } from "../components/ErrorPanel";
import { LoadingSpinner } from "../components/LoadingSpinner";
import { PageHeader } from "../components/PageHeader";
import { StatCard } from "../components/StatCard";
import { StatusChip } from "../components/StatusChip";
import { accessIqApi } from "../services/accessiq";
import { formatNumber } from "../utils/format";

export function DashboardPage() {
  const health = useQuery({ queryKey: ["health"], queryFn: accessIqApi.getHealth });
  const users = useQuery({ queryKey: ["users"], queryFn: accessIqApi.listUsers });
  const groups = useQuery({ queryKey: ["scim-groups"], queryFn: () => accessIqApi.listScimGroups(100) });
  const apps = useQuery({ queryKey: ["applications"], queryFn: accessIqApi.listApplications });
  const connectors = useQuery({ queryKey: ["connectors"], queryFn: accessIqApi.listConnectors });
  const jobs = useQuery({ queryKey: ["provisioning-jobs"], queryFn: () => accessIqApi.listProvisioningJobs(25) });
  const campaigns = useQuery({ queryKey: ["campaigns"], queryFn: () => accessIqApi.listCampaigns(25) });
  const providers = useQuery({ queryKey: ["ai-providers"], queryFn: accessIqApi.listAiProviders });

  const anyLoading = [
    health,
    users,
    groups,
    apps,
    connectors,
    jobs,
    campaigns,
    providers,
  ].some((query) => query.isLoading);

  return (
    <>
      <PageHeader title="Dashboard" eyebrow="Overview" />
      {anyLoading ? <LoadingSpinner /> : null}
      {health.error ? <ErrorPanel error={health.error} /> : null}
      <div className="stat-grid">
        <StatCard label="Users" value={users.data?.length ?? 0} />
        <StatCard label="Groups" value={groups.data?.totalResults ?? 0} />
        <StatCard label="Applications" value={apps.data?.length ?? 0} />
        <StatCard label="Provisioning Jobs" value={jobs.data?.length ?? 0} />
        <StatCard label="Connectors" value={connectors.data?.length ?? 0} />
        <StatCard label="Active Campaigns" value={campaigns.data?.filter((item) => item.status === "ACTIVE").length ?? 0} />
        <StatCard
          label="AI Provider"
          value={providers.data?.configured_provider ?? "Unavailable"}
          detail={providers.data?.enabled ? "Enabled" : "Disabled"}
        />
        <StatCard label="API Status" value={health.data?.status ?? "Unknown"} />
      </div>
      <Card title="System Health">
        <DataTable
          data={Object.entries(health.data?.subsystems ?? {})}
          getRowKey={([name]) => name}
          columns={[
            { key: "name", header: "Subsystem", render: ([name]) => name },
            {
              key: "status",
              header: "Status",
              render: ([, subsystem]) => <StatusChip status={subsystem.status} />,
            },
            {
              key: "details",
              header: "Details",
              render: ([, subsystem]) => summarizeDetails(subsystem.details),
            },
          ]}
        />
      </Card>
    </>
  );
}

function summarizeDetails(details: Record<string, unknown>): string {
  const countKeys = ["enabled_count", "event_count", "job_count", "history_count"];
  for (const key of countKeys) {
    if (typeof details[key] === "number") {
      return `${key.replace(/_/g, " ")}: ${formatNumber(details[key])}`;
    }
  }
  return Object.keys(details).length ? `${Object.keys(details).length} fields` : "No details";
}
