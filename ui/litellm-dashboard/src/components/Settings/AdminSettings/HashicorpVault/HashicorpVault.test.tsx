import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { AppRouterContext } from "next/dist/shared/lib/app-router-context.shared-runtime";
import { beforeEach, describe, expect, it, vi } from "vitest";
const mockUseAuthorized = vi.hoisted(() => vi.fn());
vi.mock("@/app/(dashboard)/hooks/useAuthorized", () => ({
  __esModule: true,
  default: mockUseAuthorized,
}));
const { default: HashicorpVault } = await import("./HashicorpVault");

const testRouter = {
  back: vi.fn(),
  forward: vi.fn(),
  refresh: vi.fn(),
  push: vi.fn(),
  replace: vi.fn(),
  prefetch: vi.fn(),
};
const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });

const renderHashicorpVault = () =>
  render(
    <AppRouterContext.Provider value={testRouter}>
      <QueryClientProvider client={queryClient}>
        <HashicorpVault />
      </QueryClientProvider>
    </AppRouterContext.Provider>,
  );

const values: Record<string, unknown> = {
  vault_addr: "https://vault.example.com",
  store_virtual_keys: false,
  prefix_for_stored_virtual_keys: "xhub/keys/",
};

vi.mock("@/app/(dashboard)/hooks/configOverrides/useHashicorpVaultConfig", () => ({
  useHashicorpVaultConfig: () => ({
    data: {
      values: {
        vault_addr: "https://vault.example.com",
        store_virtual_keys: false,
        prefix_for_stored_virtual_keys: "xhub/keys/",
      },
    },
    isLoading: false,
    isError: false,
  }),
}));

vi.mock("@/app/(dashboard)/hooks/configOverrides/useDeleteHashicorpVaultConfig", () => ({
  useDeleteHashicorpVaultConfig: () => ({ mutate: vi.fn(), isPending: false }),
}));

vi.mock("@/app/(dashboard)/hooks/configOverrides/useUpdateHashicorpVaultConfig", () => ({
  useUpdateHashicorpVaultConfig: () => ({ mutate: vi.fn(), isPending: false }),
}));

vi.mock("@/app/(dashboard)/hooks/configOverrides/hashicorpVaultApi", () => ({
  testHashicorpVaultConnection: vi.fn(),
}));

vi.mock("./EditHashicorpVaultModal", () => ({ default: () => null }));
vi.mock("@/components/common_components/DeleteResourceModal", () => ({ default: () => null }));

describe("HashicorpVault", () => {
  beforeEach(() => {
    values.store_virtual_keys = false;
    mockUseAuthorized.mockReturnValue({ accessToken: "test-token" } as any);
  });

  it("renders a false automatic storage value as Disabled instead of Not configured", () => {
    renderHashicorpVault();

    expect(screen.getByText("Hashicorp Vault")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /view documentation/i })).not.toBeInTheDocument();
  });

  it("does not expose the removed LiteLLM documentation link", () => {
    renderHashicorpVault();

    expect(screen.queryByRole("link", { name: /view documentation/i })).not.toBeInTheDocument();
  });
});
