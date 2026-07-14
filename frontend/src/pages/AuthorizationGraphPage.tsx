import { useQuery } from "@tanstack/react-query";
import { Card } from "../components/Card";
import { DataTable } from "../components/DataTable";
import { ErrorPanel } from "../components/ErrorPanel";
import { LoadingSpinner } from "../components/LoadingSpinner";
import { PageHeader } from "../components/PageHeader";
import { StatCard } from "../components/StatCard";
import { StatusChip } from "../components/StatusChip";
import { accessIqApi } from "../services/accessiq";
import { formatDateTime } from "../utils/format";

interface GraphRow {
  name: string;
  value: string | number;
}

export function AuthorizationGraphPage() {
  const cache = useQuery({
    queryKey: ["graph-cache"],
    queryFn: accessIqApi.getGraphCacheStatus,
  });
  const graph = useQuery({
    queryKey: ["graph-export"],
    queryFn: accessIqApi.getGraphExport,
  });

  const rows: GraphRow[] = [
    { name: "Cache Built", value: cache.data?.built ? "yes" : "no" },
    { name: "Built At", value: formatDateTime(cache.data?.built_at) },
    { name: "Export Nodes", value: graph.data?.nodes?.length ?? 0 },
    { name: "Export Edges", value: graph.data?.edges?.length ?? 0 },
  ];

  return (
    <>
      <PageHeader title="Authorization Graph" eyebrow="Evidence" />
      {cache.isLoading || graph.isLoading ? <LoadingSpinner /> : null}
      {cache.error ? <ErrorPanel error={cache.error} /> : null}
      {graph.error ? <ErrorPanel error={graph.error} /> : null}
      <div className="stat-grid">
        <StatCard label="Graph Nodes" value={cache.data?.node_count ?? graph.data?.nodes?.length ?? 0} />
        <StatCard label="Graph Edges" value={cache.data?.edge_count ?? graph.data?.edges?.length ?? 0} />
        <StatCard label="Cache" value={cache.data?.built ? "Built" : "Pending"} />
      </div>
      <Card title="Graph Status">
        <DataTable<GraphRow>
          data={rows}
          getRowKey={(row) => row.name}
          columns={[
            { key: "name", header: "Metric", render: (row) => row.name },
            {
              key: "value",
              header: "Value",
              render: (row) =>
                row.name === "Cache Built" ? <StatusChip status={String(row.value)} /> : row.value,
            },
          ]}
        />
      </Card>
    </>
  );
}
