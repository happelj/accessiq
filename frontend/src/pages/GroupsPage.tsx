import { useQuery } from "@tanstack/react-query";
import { Card } from "../components/Card";
import { DataTable } from "../components/DataTable";
import { ErrorPanel } from "../components/ErrorPanel";
import { LoadingSpinner } from "../components/LoadingSpinner";
import { PageHeader } from "../components/PageHeader";
import { accessIqApi } from "../services/accessiq";
import type { ScimGroup } from "../types/api";
import { formatDateTime } from "../utils/format";

export function GroupsPage() {
  const groups = useQuery({
    queryKey: ["scim-groups"],
    queryFn: () => accessIqApi.listScimGroups(100),
  });

  return (
    <>
      <PageHeader title="Groups" eyebrow="SCIM Groups" />
      {groups.isLoading ? <LoadingSpinner /> : null}
      {groups.error ? <ErrorPanel error={groups.error} /> : null}
      <Card>
        <DataTable<ScimGroup>
          data={groups.data?.Resources ?? []}
          getRowKey={(group) => group.id}
          columns={[
            { key: "displayName", header: "Display Name", render: (group) => group.displayName },
            { key: "members", header: "Members", render: (group) => group.members?.length ?? 0 },
            {
              key: "modified",
              header: "Last Modified",
              render: (group) => formatDateTime(group.meta?.lastModified),
            },
          ]}
        />
      </Card>
    </>
  );
}
