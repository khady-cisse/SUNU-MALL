// @vitest-environment jsdom
import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { Timeline, type TimelineEntry } from "./Timeline";

const entries: TimelineEntry[] = [
  {
    date: "2026-08-10T09:30:00Z",
    actor: "Modou Ndiaye",
    actorRole: "admin",
    action: "Commande créée",
    label: "#CMD-AB12",
    detail: "Paiement Wave confirmé.",
  },
  {
    date: "2026-08-10T10:00:00Z",
    action: "En cours de livraison",
  },
];

describe("Timeline", () => {
  it("shows an empty message when there are no entries", () => {
    render(<Timeline entries={[]} />);
    expect(screen.getByText("Aucun historique.")).toBeInTheDocument();
  });

  it("renders action, label, actor, role and detail", () => {
    render(<Timeline entries={entries} />);
    expect(screen.getByText("Commande créée")).toBeInTheDocument();
    expect(screen.getByText("#CMD-AB12")).toBeInTheDocument();
    expect(screen.getByText("Modou Ndiaye")).toBeInTheDocument();
    expect(screen.getByText(/admin/)).toBeInTheDocument();
    expect(screen.getByText("Paiement Wave confirmé.")).toBeInTheDocument();
    expect(screen.getByText("En cours de livraison")).toBeInTheDocument();
  });

  it("avoids rendering optional fields when absent", () => {
    render(<Timeline entries={entries.slice(1)} />);
    expect(screen.queryByText("Modou Ndiaye")).not.toBeInTheDocument();
    expect(screen.queryByText("#CMD-AB12")).not.toBeInTheDocument();
  });
});