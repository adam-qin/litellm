import { fireEvent, render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { AppRouterContext } from "next/dist/shared/lib/app-router-context.shared-runtime";
import { beforeEach, describe, expect, it, vi } from "vitest";
import EditHashicorpVaultModal from "./EditHashicorpVaultModal";

const mockUseAuthorized = vi.hoisted(() => vi.fn());
vi.mock("@/app/(dashboard)/hooks/useAuthorized", () => ({
  __esModule: true,
  default: mockUseAuthorized,
}));

const updateConfig = vi.fn();
const testRouter = {
  back: vi.fn(),
  forward: vi.fn(),
  refresh: vi.fn(),
  push: vi.fn(),
  replace: vi.fn(),
  prefetch: vi.fn(),
};
const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });

const renderEditModal = () =>
  render(
    <AppRouterContext.Provider value={testRouter}>
      <QueryClientProvider client={queryClient}>
        <EditHashicorpVaultModal isVisible onCancel={vi.fn()} onSuccess={vi.fn()} />
      </QueryClientProvider>
    </AppRouterContext.Provider>,
  );

vi.mock("@/app/(dashboard)/hooks/configOverrides/useHashicorpVaultConfig", () => ({
  useHashicorpVaultConfig: () => ({
    data: {
      values: {
        vault_addr: "https://vault.example.com",
        vault_token: "********",
        store_virtual_keys: false,
        prefix_for_stored_virtual_keys: "xhub/keys/",
      },
      field_schema: {
        properties: {
          vault_addr: { description: "Vault address", type: "string" },
          vault_token: { description: "Vault token", type: "string" },
          store_virtual_keys: { description: "Store Virtual Keys", type: "boolean" },
          prefix_for_stored_virtual_keys: { description: "Secret prefix", type: "string" },
        },
      },
    },
  }),
}));

vi.mock("@/app/(dashboard)/hooks/configOverrides/useUpdateHashicorpVaultConfig", () => ({
  useUpdateHashicorpVaultConfig: () => ({ mutate: updateConfig, isPending: false }),
}));

vi.mock("@/components/molecules/notifications_manager", () => ({
  default: { success: vi.fn(), fromBackend: vi.fn() },
}));

describe("EditHashicorpVaultModal", () => {
  beforeEach(() => {
    updateConfig.mockReset();
    mockUseAuthorized.mockReturnValue({ accessToken: "test-token" } as any);
  });

  it("initializes the automatic storage switch and submits its boolean value", async () => {
    renderEditModal();

    const switchControl = screen.getByRole("switch", {
      name: "Automatically Store Virtual Keys",
    });
    expect(switchControl).not.toBeChecked();

    fireEvent.click(switchControl);
    expect(switchControl).toBeChecked();
    expect(screen.getByText(/Virtual Key persistence is asynchronous/i)).toBeInTheDocument();
  });
});
