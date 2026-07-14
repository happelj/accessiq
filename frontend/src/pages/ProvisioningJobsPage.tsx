import { useQuery } from "@tanstack/react-query";
import { Card } from "../components/Card";
import { DataTable } from "../components/DataTable";
import { ErrorPanel } from "../components/ErrorPanel";
import { LoadingSpinner } from "../components/LoadingSpinner";
import { PageHeader } from "../components/PageHeader";
import { StatusChip } from "../components/StatusChip";
import { accessIqApi } from "../services/accessiq";
import type { ProvisioningHistory, ProvisioningJob } from "../types/api";
import { formatDateTime } from "../utils/format";

export function ProvisioningJobsPage() {
  const jobs = useQuery({
    queryKey: ["provisioning-jobs"],
    queryFn: () => accessIqApi.listProvisioningJobs(50),
  });
  const history = useQuery({
    queryKey: ["provisioning-history"],
    queryFn: () => accessIqApi.listProvisioningHistory(50),
  });

  return (
    <>
      <PageHeader title="Provisioning Jobs" eyebrow="Execution" />
      {jobs.isLoading || history.isLoading ? <LoadingSpinner /> : null}
      {jobs.error ? <ErrorPanel error={jobs.error} /> : null}
      {history.error ? <ErrorPanel error={history.error} /> : null}
      <div className="stack">
        <Card title="Jobs">
          <DataTable<ProvisioningJob>
            data={jobs.data ?? []}
            getRowKey={(job) => job.id}
            columns={[
              { key: "id", header: "ID", render: (job) => job.id },
              { key: "connector", header: "Connector", render: (job) => job.connector },
              { key: "operation", header: "Operation", render: (job) => job.operation },
              {
                key: "status",
                header: "Status",
                render: (job) => <StatusChip status={job.status} />,
              },
              {
                key: "created",
                header: "Created",
                render: (job) => formatDateTime(job.created_at),
              },
            ]}
          />
        </Card>
        <Card title="History">
          <DataTable<ProvisioningHistory>
            data={history.data ?? []}
            getRowKey={(entry) => entry.id}
            columns={[
              { key: "job", header: "Job", render: (entry) => entry.job_id },
              { key: "event", header: "Event", render: (entry) => entry.event_type },
              {
                key: "status",
                header: "Status",
                render: (entry) => <StatusChip status={entry.status} />,
              },
              { key: "message", header: "Message", render: (entry) => entry.message },
              {
                key: "created",
                header: "Created",
                render: (entry) => formatDateTime(entry.created_at),
              },
            ]}
          />
        </Card>
      </div>
    </>
  );
}
