import { EmptyState } from "./EmptyState";

export interface DataTableColumn<T> {
  key: string;
  header: string;
  render: (row: T) => React.ReactNode;
  align?: "left" | "right";
}

interface DataTableProps<T> {
  columns: Array<DataTableColumn<T>>;
  data: T[];
  getRowKey: (row: T) => string | number;
  emptyTitle?: string;
}

export function DataTable<T>({
  columns,
  data,
  getRowKey,
  emptyTitle = "No records found",
}: DataTableProps<T>) {
  if (data.length === 0) {
    return <EmptyState title={emptyTitle} />;
  }

  return (
    <div className="table-wrap">
      <table className="data-table">
        <thead>
          <tr>
            {columns.map((column) => (
              <th
                key={column.key}
                className={column.align === "right" ? "align-right" : ""}
              >
                {column.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {data.map((row) => (
            <tr key={getRowKey(row)}>
              {columns.map((column) => (
                <td
                  key={column.key}
                  className={column.align === "right" ? "align-right" : ""}
                >
                  {column.render(row)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
