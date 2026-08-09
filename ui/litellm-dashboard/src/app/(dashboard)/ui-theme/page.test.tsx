import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import UITheme from "./page";

const { mockUseAuthorized, state, mockUIThemeSettings } = vi.hoisted(() => {
  const state = {
    accessToken: "token-123" as string | null,
    userRole: "Admin",
    userId: "user-123" as string | null,
  };
  return {
    state,
    mockUseAuthorized: vi.fn(() => ({
      accessToken: state.accessToken,
      userRole: state.userRole,
      userId: state.userId,
    })),
    mockUIThemeSettings: vi.fn(
      ({ accessToken, userRole, userID }: { accessToken: string | null; userRole: string; userID: string | null }) => (
        <div data-testid="ui-theme-settings">
          {accessToken}:{userRole}:{userID}
        </div>
      ),
    ),
  };
});

vi.mock("@/app/(dashboard)/hooks/useAuthorized", () => ({ default: mockUseAuthorized }));
vi.mock("./UIThemeSettings", () => ({ default: mockUIThemeSettings }));

describe("UI theme page access guard", () => {
  afterEach(() => {
    state.accessToken = "token-123";
    state.userRole = "Admin";
    state.userId = "user-123";
    vi.clearAllMocks();
  });

  it("renders theme settings for a writable administrator", () => {
    render(<UITheme />);

    expect(screen.getByTestId("ui-theme-settings")).toHaveTextContent("token-123:Admin:user-123");
  });

  it.each(["Admin Viewer", "proxy_admin_viewer", "Org Admin", "Internal User"])(
    "blocks %s from the writable theme settings page",
    (userRole) => {
      state.userRole = userRole;
      render(<UITheme />);

      expect(screen.getByText("无权修改界面主题。")).toBeInTheDocument();
      expect(screen.queryByTestId("ui-theme-settings")).not.toBeInTheDocument();
      expect(mockUIThemeSettings).not.toHaveBeenCalled();
    },
  );
});
