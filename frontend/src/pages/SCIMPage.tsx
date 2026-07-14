import { useQuery } from "@tanstack/react-query";
import { Card } from "../components/Card";
import { DataTable } from "../components/DataTable";
import { ErrorPanel } from "../components/ErrorPanel";
import { LoadingSpinner } from "../components/LoadingSpinner";
import { PageHeader } from "../components/PageHeader";
import { StatusChip } from "../components/StatusChip";
import { accessIqApi } from "../services/accessiq";

interface ScimRow {
  name: string;
  value: string;
}

export function SCIMPage() {
  const serviceProvider = useQuery({
    queryKey: ["scim-service-provider"],
    queryFn: accessIqApi.getScimServiceProviderConfig,
  });
  const resourceTypes = useQuery({
    queryKey: ["scim-resource-types"],
    queryFn: accessIqApi.getScimResourceTypes,
  });
  const schemas = useQuery({
    queryKey: ["scim-schemas"],
    queryFn: accessIqApi.getScimSchemas,
  });

  const rows: ScimRow[] = [
    {
      name: "Service Provider Config",
      value: serviceProvider.data ? "Available" : "Pending",
    },
    { name: "Resource Types", value: resourceTypes.data ? "Available" : "Pending" },
    { name: "Schemas", value: schemas.data ? "Available" : "Pending" },
  ];

  return (
    <>
      <PageHeader title="SCIM" eyebrow="Protocol" />
      {[serviceProvider, resourceTypes, schemas].some((query) => query.isLoading) ? (
        <LoadingSpinner />
      ) : null}
      {serviceProvider.error ? <ErrorPanel error={serviceProvider.error} /> : null}
      {resourceTypes.error ? <ErrorPanel error={resourceTypes.error} /> : null}
      {schemas.error ? <ErrorPanel error={schemas.error} /> : null}
      <Card title="SCIM Metadata">
        <DataTable<ScimRow>
          data={rows}
          getRowKey={(row) => row.name}
          columns={[
            { key: "name", header: "Endpoint", render: (row) => row.name },
            {
              key: "value",
              header: "Status",
              render: (row) => <StatusChip status={row.value.toLowerCase()} />,
            },
          ]}
        />
      </Card>
    </>
  );
}
