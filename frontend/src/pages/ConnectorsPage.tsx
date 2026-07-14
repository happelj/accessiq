import { useQueries, useQuery } from "@tanstack/react-query";
import { Card } from "../components/Card";
import { DataTable } from "../components/DataTable";
import { ErrorPanel } from "../components/ErrorPanel";
import { LoadingSpinner } from "../components/LoadingSpinner";
import { PageHeader } from "../components/PageHeader";
import { StatusChip } from "../components/StatusChip";
import { accessIqApi } from "../services/accessiq";
import type { Connector } from "../types/api";

export function ConnectorsPage() {
  const connectors = useQuery({
    queryKey: ["connectors"],
    queryFn: accessIqApi.listConnectors,
  });
  const healthChecks = useQueries({
    queries: (connectors.data ?? []).map((connector) => ({
      queryKey: ["connector-health", connector.name],
      queryFn: () => accessIqApi.getConnectorHealth(connector.name),
      enabled: Boolean(connector.name),
    })),
  });

  return (
    <>
      <PageHeader title="Connectors" eyebrow="Provisioning" />
      {connectors.isLoading ? <LoadingSpinner /> : null}
      {connectors.error ? <ErrorPanel error={connectors.error} /> : null}
      <Card>
        <DataTable<Connector>
          data={connectors.data ?? []}
          getRowKey={(connector) => connector.name}
          columns={[
            {
              key: "name",
              header: "Connector",
              render: (connector) => connector.display_name,
            },
            {
              key: "enabled",
              header: "Enabled",
              render: (connector) => <StatusChip status={connector.enabled} />,
            },
            {
              key: "health",
              header: "Health",
              render: (connector) => (
                <StatusChip
                  status={
                    healthChecks.find(
                      (query) => query.data?.connector === connector.name,
                    )?.data?.status ?? "pending"
                  }
                />
              ),
            },
            {
              key: "operations",
              header: "Operations",
              render: (connector) => connector.supported_operations.length,
              align: "right",
            },
          ]}
        />
      </Card>
    </>
  );
}
