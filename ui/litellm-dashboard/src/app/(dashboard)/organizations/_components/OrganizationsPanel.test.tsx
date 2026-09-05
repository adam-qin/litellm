import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import React from "react";
import { describe, expect, it, vi } from "vitest";

vi.mock("@/components/vector_store_management/VectorStoreSelector", () => ({
  __esModule: true,
  default: () => null,
}));
vi.mock("@/components/mcp_server_management/MCPServerSelector", () => ({
  __esModule: true,
  default: () => null,
}));
vi.mock("@/app/(dashboard)/hooks/useAuthorized", () => ({
  default: () => ({
    accessToken: null,
    userId: null,
    userRole: null,
  }),
}));
vi.mock("./OrganizationsTable", () => ({
  __esModule: true,
  default: (props: { isLoading: boolean }) => (
    <div data-testid="organizations-table">isLoading:{String(props.isLoading)}</div>
  ),
}));

import OrganizationsPanel from "./OrganizationsPanel";

const renderWithQueryClient = (ui: React.ReactElement) => {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(<QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>);
};

describe("OrganizationsPanel", () => {
  it("shows the create button for an admin without a premium license", () => {
    renderWithQueryClient(<OrganizationsPanel userRole="Admin" accessToken={null} />);

    expect(screen.queryByText(/LiteLLM Enterprise feature/i)).not.toBeInTheDocument();
    expect(screen.getByText("+ Create New Organization")).toBeInTheDocument();
  });

  it("shows the create button for an org admin", () => {
    renderWithQueryClient(<OrganizationsPanel userRole="Org Admin" accessToken={null} />);

    expect(screen.getByText("+ Create New Organization")).toBeInTheDocument();
  });

  it("hides the create button from internal users", () => {
    renderWithQueryClient(<OrganizationsPanel userRole="Internal User" accessToken={null} />);

    expect(screen.queryByText("+ Create New Organization")).not.toBeInTheDocument();
  });

  it("resolves the loading skeleton to false when the query is disabled (no token)", () => {
    renderWithQueryClient(<OrganizationsPanel userRole="Admin" accessToken={null} />);

    // A disabled React Query keeps isPending true forever; feeding isLoading avoids a stuck skeleton.
    expect(screen.getByTestId("organizations-table")).toHaveTextContent("isLoading:false");
  });
});
