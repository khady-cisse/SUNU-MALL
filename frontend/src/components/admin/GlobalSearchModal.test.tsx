// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, fireEvent, act } from "@testing-library/react";
import { MemoryRouter, Routes, Route, useLocation } from "react-router-dom";
import { GlobalSearchModal } from "./GlobalSearchModal";
import { apiGet } from "@/lib/api";

vi.mock("@/lib/api", () => ({ apiGet: vi.fn() }));

const mockedGet = vi.mocked(apiGet);

function LocationProbe() {
  const location = useLocation();
  return <div data-testid="location">{location.pathname}</div>;
}

function renderModal() {
  return render(
    <MemoryRouter initialEntries={["/"]}>
      <Routes>
        <Route path="/" element={<GlobalSearchModal />} />
        <Route path="/admin-users/:id" element={<div>USER PAGE</div>} />
      </Routes>
      <LocationProbe />
    </MemoryRouter>,
  );
}

function openWithCtrlK() {
  fireEvent.keyDown(window, { key: "k", ctrlKey: true });
}

const input = () => screen.getByPlaceholderText(
  "Rechercher un utilisateur, vendeur, commande, produit, plainte...",
);

describe("GlobalSearchModal", () => {
  beforeEach(() => {
    mockedGet.mockReset();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("is closed by default", () => {
    renderModal();
    expect(screen.queryByPlaceholderText(/Rechercher un utilisateur/)).not.toBeInTheDocument();
  });

  it("opens with Ctrl+K and explains the minimum length", () => {
    renderModal();
    openWithCtrlK();
    expect(input()).toBeInTheDocument();
    expect(screen.getByText(/Tapez au moins 2 caractères/)).toBeInTheDocument();
  });

  it("renders grouped results once the query is long enough", async () => {
    vi.useFakeTimers();
    mockedGet.mockResolvedValue({
      users: [{ type: "users", label: "Jeanne Wade", subtitle: "jeanne@mail.com", to: "/admin-users/123" }],
      orders: [{ type: "orders", label: "Commande #abc", subtitle: "Tech World — 2500 FCFA", to: "/admin-order-detail?order=abc" }],
    });
    renderModal();
    openWithCtrlK();

    fireEvent.change(input(), { target: { value: "jeanne" } });
    await act(async () => {
      vi.advanceTimersByTime(260);
    });

    expect(mockedGet).toHaveBeenCalledWith("/search/?q=jeanne");
    expect(screen.getByText("UTILISATEURS")).toBeInTheDocument();
    expect(screen.getByText("COMMANDES")).toBeInTheDocument();
    expect(screen.getByText("Jeanne Wade")).toBeInTheDocument();
    expect(screen.getByText("jeanne@mail.com")).toBeInTheDocument();
  });

  it("navigates when a result is clicked", async () => {
    vi.useFakeTimers();
    mockedGet.mockResolvedValue({
      users: [{ type: "users", label: "Jeanne Wade", to: "/admin-users/123" }],
    });
    renderModal();
    openWithCtrlK();

    fireEvent.change(input(), { target: { value: "jeanne" } });
    await act(async () => {
      vi.advanceTimersByTime(260);
    });

    fireEvent.click(screen.getByText("Jeanne Wade"));
    expect(screen.getByText("USER PAGE")).toBeInTheDocument();
  });

  it("shows an empty message when the search returns nothing", async () => {
    vi.useFakeTimers();
    mockedGet.mockResolvedValue({});
    renderModal();
    openWithCtrlK();

    fireEvent.change(input(), { target: { value: "zz" } });
    await act(async () => {
      vi.advanceTimersByTime(260);
    });

    expect(screen.getByText("Aucun résultat trouvé.")).toBeInTheDocument();
  });

  it("closes with Escape", () => {
    renderModal();
    openWithCtrlK();
    expect(input()).toBeInTheDocument();

    fireEvent.keyDown(window, { key: "Escape" });
    expect(screen.queryByPlaceholderText(/Rechercher un utilisateur/)).not.toBeInTheDocument();
  });

  it("closes when clicking the backdrop", () => {
    renderModal();
    openWithCtrlK();
    expect(input()).toBeInTheDocument();

    const backdrop = input().closest(".fixed") as HTMLElement;
    fireEvent.click(backdrop);
    expect(screen.queryByPlaceholderText(/Rechercher un utilisateur/)).not.toBeInTheDocument();
  });
});