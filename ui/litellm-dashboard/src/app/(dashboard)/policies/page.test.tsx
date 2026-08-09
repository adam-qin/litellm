import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import Policies from "./page";

const { mockUseAuthorized, state, mockPoliciesPanel } = vi.hoisted(() => {
  const state = {
    accessToken: "token-123" as string | null,
    userRole: "Admin",
  };
  return {
    state,
    mockUseAuthorized: vi.fn(() => ({
      accessToken: state.accessToken,
      userRole: state.userRole,
    })),
    mockPoliciesPanel: vi.fn(({ accessToken, userRole }: { accessToken: string | null; userRole: string }) => (
      <div data-testid="policies-panel">
        {accessToken}:{userRole}
      </div>
    )),
  };
});

vi.mock("@/app/(dashboard)/hooks/useAuthorized", () => ({ default: mockUseAuthorized }));
vi.mock("./_components", () => ({ default: mockPoliciesPanel }));

describe("Policies page access guard", () => {
  afterEach(() => {
    state.accessToken = "token-123";
    state.userRole = "Admin";
    vi.clearAllMocks();
  });

  it("renders the panel for an administrator", () => {
    render(<Policies />);

    expect(screen.getByTestId("policies-panel")).toHaveTextContent("token-123:Admin");
    expect(mockPoliciesPanel).toHaveBeenCalledTimes(1);
    expect(mockPoliciesPanel.mock.calls[0]?.[0]).toEqual({
      accessToken: "token-123",
      userRole: "Admin",
    });
  });

  it.each(["Internal User", "Org User", "Undefined Role"])("blocks %s from direct policy access", (userRole) => {
    state.userRole = userRole;
    render(<Policies />);

    expect(screen.getByText("无权访问策略管理。")).toBeInTheDocument();
    expect(screen.queryByTestId("policies-panel")).not.toBeInTheDocument();
    expect(mockPoliciesPanel).not.toHaveBeenCalled();
  });

  it("allows an admin viewer to open the page for read-only rendering", () => {
    state.userRole = "Admin Viewer";
    render(<Policies />);

    expect(screen.getByTestId("policies-panel")).toHaveTextContent("token-123:Admin Viewer");
  });
});
