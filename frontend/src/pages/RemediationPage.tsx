import { useQuery } from "@tanstack/react-query";
import { Card } from "../components/Card";
import { DataTable } from "../components/DataTable";
import { ErrorPanel } from "../components/ErrorPanel";
import { LoadingSpinner } from "../components/LoadingSpinner";
import { PageHeader } from "../components/PageHeader";
import { StatusChip } from "../components/StatusChip";
import { accessIqApi } from "../services/accessiq";
import type { RemediationJob } from "../types/api";
import { formatDateTime } from "../utils/format";

export function RemediationPage() {
  const remediationJobs = useQuery({
    queryKey: ["remediation-jobs"],
    queryFn: () => accessIqApi.listRemediationJobs(50),
  });

  return (
    <>
      <PageHeader title="Remediation" eyebrow="Governance Actions" />
      {remediationJobs.isLoading ? <LoadingSpinner /> : null}
      {remediationJobs.error ? <ErrorPanel error={remediationJobs.error} /> : null}
      <Card>
        <DataTable<RemediationJob>
          data={remediationJobs.data ?? []}
          getRowKey={(job) => job.id}
          columns={[
            { key: "id", header: "ID", render: (job) => job.id },
            { key: "campaign", header: "Campaign", render: (job) => job.campaign_id },
            { key: "type", header: "Type", render: (job) => job.remediation_type },
            { key: "status", header: "Status", render: (job) => <StatusChip status={job.status} /> },
            { key: "created", header: "Created", render: (job) => formatDateTime(job.created_at) },
          ]}
        />
      </Card>
    </>
  );
}
