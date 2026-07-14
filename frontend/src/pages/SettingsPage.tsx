import { useQuery } from "@tanstack/react-query";
import { Card } from "../components/Card";
import { DataTable } from "../components/DataTable";
import { ErrorPanel } from "../components/ErrorPanel";
import { LoadingSpinner } from "../components/LoadingSpinner";
import { PageHeader } from "../components/PageHeader";
import { StatusChip } from "../components/StatusChip";
import { API_BASE_URL, APP_ENV } from "../config/env";
import { useAuth } from "../contexts/AuthContext";
import { accessIqApi } from "../services/accessiq";

interface SettingRow {
  name: string;
  value: string;
}

export function SettingsPage() {
  const auth = useAuth();
  const providers = useQuery({
    queryKey: ["ai-providers"],
    queryFn: accessIqApi.listAiProviders,
  });

  const rows: SettingRow[] = [
    { name: "Environment", value: APP_ENV },
    { name: "API Base URL", value: API_BASE_URL },
    { name: "Current User", value: auth.currentUser?.email ?? "Unknown" },
    { name: "Operator Role", value: auth.currentUser?.operator_role ?? "Unknown" },
    { name: "Token Refresh", value: "Placeholder" },
  ];

  return (
    <>
      <PageHeader title="Settings" eyebrow="Configuration" />
      <div className="two-column">
        <Card title="Frontend">
          <DataTable<SettingRow>
            data={rows}
            getRowKey={(row) => row.name}
            columns={[
              { key: "name", header: "Name", render: (row) => row.name },
              { key: "value", header: "Value", render: (row) => row.value },
            ]}
          />
        </Card>
        <Card title="AI Providers">
          {providers.isLoading ? <LoadingSpinner /> : null}
          {providers.error ? <ErrorPanel error={providers.error} /> : null}
          <DataTable
            data={providers.data?.providers ?? []}
            getRowKey={(provider) => provider.provider}
            columns={[
              {
                key: "name",
                header: "Name",
                render: (provider) => provider.metadata.display_name,
              },
              {
                key: "status",
                header: "Status",
                render: (provider) => <StatusChip status={provider.status} />,
              },
              {
                key: "available",
                header: "Available",
                render: (provider) => (
                  <StatusChip status={provider.metadata.available} />
                ),
              },
            ]}
          />
        </Card>
      </div>
    </>
  );
}
