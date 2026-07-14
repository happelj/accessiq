import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Card } from "../components/Card";
import { DataTable } from "../components/DataTable";
import { ErrorPanel } from "../components/ErrorPanel";
import { LoadingSpinner } from "../components/LoadingSpinner";
import { PageHeader } from "../components/PageHeader";
import { accessIqApi } from "../services/accessiq";
import type { Application, Entitlement } from "../types/api";

export function ApplicationsPage() {
  const applications = useQuery({
    queryKey: ["applications"],
    queryFn: accessIqApi.listApplications,
  });
  const [selectedApplicationId, setSelectedApplicationId] = useState<number | null>(null);
  const selectedApplication =
    applications.data?.find((application) => application.id === selectedApplicationId) ??
    applications.data?.[0];
  const entitlements = useQuery({
    queryKey: ["entitlements", selectedApplication?.id],
    queryFn: () => accessIqApi.listEntitlements(selectedApplication?.id ?? 0),
    enabled: Boolean(selectedApplication?.id),
  });

  return (
    <>
      <PageHeader title="Applications" eyebrow="Catalog" />
      {applications.isLoading ? <LoadingSpinner /> : null}
      {applications.error ? <ErrorPanel error={applications.error} /> : null}
      <div className="two-column">
        <Card title="Applications">
          <DataTable<Application>
            data={applications.data ?? []}
            getRowKey={(application) => application.id}
            columns={[
              {
                key: "name",
                header: "Name",
                render: (application) => (
                  <button
                    type="button"
                    className="table-link"
                    onClick={() => setSelectedApplicationId(application.id)}
                  >
                    {application.name}
                  </button>
                ),
              },
              { key: "slug", header: "Slug", render: (application) => application.slug },
            ]}
          />
        </Card>
        <Card title={selectedApplication ? `${selectedApplication.name} Entitlements` : "Entitlements"}>
          {entitlements.isLoading ? <LoadingSpinner /> : null}
          {entitlements.error ? <ErrorPanel error={entitlements.error} /> : null}
          <DataTable<Entitlement>
            data={entitlements.data ?? []}
            getRowKey={(entitlement) => entitlement.id}
            columns={[
              { key: "name", header: "Name", render: (entitlement) => entitlement.name },
              { key: "slug", header: "Slug", render: (entitlement) => entitlement.slug },
            ]}
          />
        </Card>
      </div>
    </>
  );
}
