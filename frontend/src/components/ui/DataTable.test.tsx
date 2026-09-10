// @vitest-environment jsdom
import { describe, expect, it, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { DataTable, type Column } from "./DataTable";

interface Row extends Record<string, unknown> {
  id: string;
  name: string;
  price: number;
}

const columns: Column<Row>[] = [
  { key: "id", label: "ID" },
  { key: "name", label: "Nom", sortable: true },
  { key: "price", label: "Prix" },
];

const rows: Row[] = [
  { id: "r1", name: "Riz", price: 1500 },
  { id: "r2", name: "Huile", price: 3000 },
];

describe("DataTable", () => {
  it("renders headers and data rows", () => {
    render(<DataTable columns={columns} data={rows} />);
    for (const label of ["ID", "Nom", "Prix"]) {
      expect(screen.getByText(label)).toBeInTheDocument();
    }
    expect(screen.getByText("Riz")).toBeInTheDocument();
    expect(screen.getByText("Huile")).toBeInTheDocument();
    expect(screen.getByText("1500")).toBeInTheDocument();
  });

  it("uses the column render when provided", () => {
    const custom: Column<Row>[] = [
      { key: "name", label: "Nom", render: (row) => <strong>★ {row.name}</strong> },
    ];
    render(<DataTable columns={custom} data={[rows[0]]} />);
    expect(screen.getByText("★ Riz")).toBeInTheDocument();
  });

  it("falls back to an em dash for missing values", () => {
    const sparse: Column<Row>[] = [{ key: "missing", label: "Absent" }];
    render(<DataTable columns={sparse} data={rows} />);
    expect(screen.getAllByText("—")).toHaveLength(2);
  });

  it("shows the empty state when there is no data", () => {
    render(<DataTable columns={columns} data={[]} emptyDescription="Créez votre premier élément." />);
    expect(screen.getByText("Aucun résultat trouvé")).toBeInTheDocument();
    expect(screen.getByText("Créez votre premier élément.")).toBeInTheDocument();
  });

  it("shows the error state instead of rows", () => {
    render(<DataTable columns={columns} data={rows} error={new Error("Boom")} onRetry={vi.fn()} />);
    expect(screen.getByText("Boom")).toBeInTheDocument();
    expect(screen.queryByText("Riz")).not.toBeInTheDocument();
  });

  it("renders skeleton rows while loading", () => {
    render(<DataTable columns={columns} data={rows} loading />);
    expect(screen.queryByText("Riz")).not.toBeInTheDocument();
  });

  it("sorts when clicking a sortable column header", () => {
    const onSort = vi.fn();
    render(<DataTable columns={columns} data={rows} onSort={onSort} />);
    fireEvent.click(screen.getByText("Nom"));
    expect(onSort).toHaveBeenCalledWith("name");
  });

  it("navigates pages through the pagination controls", () => {
    const onPageChange = vi.fn();
    render(<DataTable columns={columns} data={rows} page={2} totalPages={3} onPageChange={onPageChange} />);
    fireEvent.click(screen.getByLabelText("Page suivante"));
    expect(onPageChange).toHaveBeenCalledWith(3);
    fireEvent.click(screen.getByText("1"));
    expect(onPageChange).toHaveBeenCalledWith(1);
  });

  it("disables the previous page button on the first page", () => {
    render(<DataTable columns={columns} data={rows} page={1} totalPages={3} onPageChange={vi.fn()} />);
    expect(screen.getByLabelText("Page précédente")).toBeDisabled();
  });

  it("changes the page size via the select", () => {
    const onPageSizeChange = vi.fn();
    render(
      <DataTable
        columns={columns}
        data={rows}
        pageSizeOptions={[10, 25, 50]}
        pageSize={25}
        onPageSizeChange={onPageSizeChange}
      />,
    );
    fireEvent.change(screen.getByRole("combobox"), { target: { value: "50" } });
    expect(onPageSizeChange).toHaveBeenCalledWith(50);
  });

  it("shows the total result count", () => {
    render(<DataTable columns={columns} data={rows} totalItems={2} />);
    expect(screen.getByText("2 résultats")).toBeInTheDocument();
  });

  it("calls onRowClick with the clicked row", () => {
    const onRowClick = vi.fn();
    render(<DataTable columns={columns} data={rows} onRowClick={onRowClick} />);
    fireEvent.click(screen.getByText("Huile"));
    expect(onRowClick).toHaveBeenCalledWith(rows[1]);
  });
});