import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { DataTable } from "./DataTable";

describe("DataTable", () => {
  it("renders rows with configured columns", () => {
    render(
      <DataTable
        data={[{ id: 1, name: "Salesforce" }]}
        getRowKey={(row) => row.id}
        columns={[{ key: "name", header: "Name", render: (row) => row.name }]}
      />,
    );

    expect(screen.getByRole("columnheader", { name: "Name" })).toBeInTheDocument();
    expect(screen.getByText("Salesforce")).toBeInTheDocument();
  });

  it("renders an empty state", () => {
    render(
      <DataTable
        data={[]}
        getRowKey={(row: { id: number }) => row.id}
        columns={[{ key: "name", header: "Name", render: (row) => row.id }]}
        emptyTitle="No applications"
      />,
    );

    expect(screen.getByText("No applications")).toBeInTheDocument();
  });
});
