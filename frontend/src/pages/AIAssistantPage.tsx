import { FormEvent, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { Card } from "../components/Card";
import { DataTable } from "../components/DataTable";
import { EmptyState } from "../components/EmptyState";
import { ErrorPanel } from "../components/ErrorPanel";
import { LoadingSpinner } from "../components/LoadingSpinner";
import { PageHeader } from "../components/PageHeader";
import { StatusChip } from "../components/StatusChip";
import { accessIqApi } from "../services/accessiq";
import type { AIEvidence, Citation } from "../types/api";

export function AIAssistantPage() {
  const providers = useQuery({
    queryKey: ["ai-providers"],
    queryFn: accessIqApi.listAiProviders,
  });
  const [question, setQuestion] = useState("Why does user 1 have access?");
  const [userId, setUserId] = useState("1");
  const [provider, setProvider] = useState("");
  const explanation = useMutation({
    mutationFn: () =>
      accessIqApi.explain({
        question,
        provider: provider || undefined,
        user_id: userId ? Number(userId) : undefined,
        max_tokens: 800,
      }),
  });

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    explanation.mutate();
  }

  return (
    <>
      <PageHeader title="AI Assistant" eyebrow="Grounded Explanation" />
      {providers.error ? <ErrorPanel error={providers.error} /> : null}
      <div className="two-column">
        <Card title="Question">
          <form className="form-stack" onSubmit={handleSubmit}>
            <label>
              Question
              <textarea
                value={question}
                rows={6}
                onChange={(event) => setQuestion(event.target.value)}
                required
              />
            </label>
            <label>
              User ID
              <input
                type="number"
                min="1"
                value={userId}
                onChange={(event) => setUserId(event.target.value)}
              />
            </label>
            <label>
              Provider
              <select value={provider} onChange={(event) => setProvider(event.target.value)}>
                <option value="">Configured provider</option>
                {(providers.data?.providers ?? []).map((item) => (
                  <option key={item.provider} value={item.provider}>
                    {item.metadata.display_name}
                  </option>
                ))}
              </select>
            </label>
            <button
              type="submit"
              className="primary-button"
              disabled={explanation.isPending}
            >
              {explanation.isPending ? "Explaining" : "Submit"}
            </button>
          </form>
        </Card>
        <Card title="Providers">
          {providers.isLoading ? <LoadingSpinner /> : null}
          <DataTable
            data={providers.data?.providers ?? []}
            getRowKey={(item) => item.provider}
            columns={[
              { key: "provider", header: "Provider", render: (item) => item.metadata.display_name },
              { key: "status", header: "Status", render: (item) => <StatusChip status={item.status} /> },
              { key: "model", header: "Model", render: (item) => item.metadata.model ?? "Not set" },
            ]}
          />
        </Card>
      </div>
      {explanation.error ? <ErrorPanel error={explanation.error} /> : null}
      {explanation.data ? (
        <div className="stack">
          <Card title={`Answer from ${explanation.data.provider.display_name}`}>
            <p className="answer-text">{explanation.data.answer}</p>
          </Card>
          <Card title="Citations">
            <DataTable<Citation>
              data={explanation.data.citations}
              getRowKey={(citation) => citation.id}
              columns={[
                { key: "title", header: "Title", render: (citation) => citation.title },
                { key: "reference", header: "Reference", render: (citation) => citation.reference },
              ]}
            />
          </Card>
          <Card title="Evidence">
            <DataTable<AIEvidence>
              data={explanation.data.evidence}
              getRowKey={(evidence) => evidence.id}
              columns={[
                { key: "type", header: "Type", render: (evidence) => evidence.evidence_type },
                { key: "title", header: "Title", render: (evidence) => evidence.title },
                { key: "reference", header: "Reference", render: (evidence) => evidence.reference },
                { key: "rank", header: "Rank", render: (evidence) => evidence.rank_score, align: "right" },
              ]}
            />
          </Card>
        </div>
      ) : (
        <EmptyState title="No explanation yet" detail="Submit a grounded question to see an answer." />
      )}
    </>
  );
}
