import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Card } from "../components/Card";
import { DataTable } from "../components/DataTable";
import { ErrorPanel } from "../components/ErrorPanel";
import { LoadingSpinner } from "../components/LoadingSpinner";
import { PageHeader } from "../components/PageHeader";
import { StatusChip } from "../components/StatusChip";
import { accessIqApi } from "../services/accessiq";
import type { AccessAssignment } from "../types/api";
import { formatDateTime } from "../utils/format";

export function AccessPage() {
  const users = useQuery({ queryKey: ["users"], queryFn: accessIqApi.listUsers });
  const [selectedUserId, setSelectedUserId] = useState<number | null>(null);
  const effectiveUserId = selectedUserId ?? users.data?.[0]?.id ?? null;
  const selectedUser = useMemo(
    () => users.data?.find((user) => user.id === effectiveUserId),
    [effectiveUserId, users.data],
  );
  const access = useQuery({
    queryKey: ["user-access", effectiveUserId],
    queryFn: () => accessIqApi.listUserAccess(effectiveUserId ?? 0),
    enabled: Boolean(effectiveUserId),
  });

  return (
    <>
      <PageHeader
        title="Access"
        eyebrow="Assignments"
        actions={
          <label className="select-control">
            User
            <select
              value={effectiveUserId ?? ""}
              onChange={(event) => setSelectedUserId(Number(event.target.value))}
            >
              {(users.data ?? []).map((user) => (
                <option key={user.id} value={user.id}>
                  {user.name}
                </option>
              ))}
            </select>
          </label>
        }
      />
      {users.isLoading || access.isLoading ? <LoadingSpinner /> : null}
      {users.error ? <ErrorPanel error={users.error} /> : null}
      {access.error ? <ErrorPanel error={access.error} /> : null}
      <Card title={selectedUser ? `${selectedUser.name} Access` : "User Access"}>
        <DataTable<AccessAssignment>
          data={access.data ?? []}
          getRowKey={(assignment) => assignment.id}
          columns={[
            {
              key: "application",
              header: "Application",
              render: (assignment) => assignment.application,
            },
            {
              key: "entitlement",
              header: "Entitlement",
              render: (assignment) => assignment.entitlement,
            },
            {
              key: "status",
              header: "Status",
              render: (assignment) => <StatusChip status={assignment.status} />,
            },
            {
              key: "granted",
              header: "Granted",
              render: (assignment) => formatDateTime(assignment.granted_at),
            },
          ]}
        />
      </Card>
    </>
  );
}
