import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Badge } from "../components/Badge";
import { Card } from "../components/Card";
import { DataTable } from "../components/DataTable";
import { ErrorPanel } from "../components/ErrorPanel";
import { LoadingSpinner } from "../components/LoadingSpinner";
import { PageHeader } from "../components/PageHeader";
import { SearchBox } from "../components/SearchBox";
import { StatusChip } from "../components/StatusChip";
import { accessIqApi } from "../services/accessiq";
import type { User } from "../types/api";

export function UsersPage() {
  const [search, setSearch] = useState("");
  const users = useQuery({ queryKey: ["users"], queryFn: accessIqApi.listUsers });
  const filteredUsers = useMemo(
    () =>
      (users.data ?? []).filter((user) =>
        [user.name, user.email, user.department, user.operator_role]
          .join(" ")
          .toLowerCase()
          .includes(search.toLowerCase()),
      ),
    [search, users.data],
  );

  return (
    <>
      <PageHeader
        title="Users"
        eyebrow="Directory"
        actions={
          <SearchBox
            label="Search users"
            value={search}
            onChange={setSearch}
            placeholder="Name, email, department"
          />
        }
      />
      {users.isLoading ? <LoadingSpinner /> : null}
      {users.error ? <ErrorPanel error={users.error} /> : null}
      <Card>
        <DataTable<User>
          data={filteredUsers}
          getRowKey={(user) => user.id}
          columns={[
            { key: "name", header: "Name", render: (user) => user.name },
            { key: "email", header: "Email", render: (user) => user.email },
            {
              key: "department",
              header: "Department",
              render: (user) => user.department,
            },
            {
              key: "role",
              header: "Role",
              render: (user) => <Badge tone="blue">{user.operator_role}</Badge>,
            },
            {
              key: "active",
              header: "Status",
              render: (user) => <StatusChip status={user.active} />,
            },
          ]}
        />
      </Card>
    </>
  );
}
