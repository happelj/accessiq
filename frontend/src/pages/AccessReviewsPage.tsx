import { useQuery } from "@tanstack/react-query";
import { Card } from "../components/Card";
import { DataTable } from "../components/DataTable";
import { ErrorPanel } from "../components/ErrorPanel";
import { LoadingSpinner } from "../components/LoadingSpinner";
import { PageHeader } from "../components/PageHeader";
import { StatusChip } from "../components/StatusChip";
import { accessIqApi } from "../services/accessiq";
import type { Campaign } from "../types/api";
import { formatDateTime } from "../utils/format";

export function AccessReviewsPage() {
  const campaigns = useQuery({
    queryKey: ["campaigns"],
    queryFn: () => accessIqApi.listCampaigns(50),
  });

  return (
    <>
      <PageHeader title="Access Reviews" eyebrow="Governance" />
      {campaigns.isLoading ? <LoadingSpinner /> : null}
      {campaigns.error ? <ErrorPanel error={campaigns.error} /> : null}
      <Card>
        <DataTable<Campaign>
          data={campaigns.data ?? []}
          getRowKey={(campaign) => campaign.id}
          columns={[
            { key: "name", header: "Campaign", render: (campaign) => campaign.name },
            { key: "status", header: "Status", render: (campaign) => <StatusChip status={campaign.status} /> },
            { key: "items", header: "Items", render: (campaign) => campaign.total_items, align: "right" },
            {
              key: "completion",
              header: "Completion",
              render: (campaign) => `${campaign.completion_percentage}%`,
              align: "right",
            },
            { key: "created", header: "Created", render: (campaign) => formatDateTime(campaign.created_at) },
          ]}
        />
      </Card>
    </>
  );
}
