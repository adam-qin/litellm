import useAuthorized from "@/app/(dashboard)/hooks/useAuthorized";
import { getLDAPSettings, updateLDAPSettings } from "@/components/networking";
import NotificationsManager from "@/components/molecules/notifications_manager";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { renderWithProviders } from "../../../../../tests/test-utils";
import LDAPSettings from "./LDAPSettings";

vi.mock("@/app/(dashboard)/hooks/useAuthorized", () => ({
  default: vi.fn(),
}));

vi.mock("@/components/networking", () => ({
  getLDAPSettings: vi.fn(),
  updateLDAPSettings: vi.fn(),
}));

vi.mock("@/components/molecules/notifications_manager", () => ({
  default: {
    success: vi.fn(),
    error: vi.fn(),
  },
}));

const mockUseAuthorized = vi.mocked(useAuthorized);
const mockGetLDAPSettings = vi.mocked(getLDAPSettings);
const mockUpdateLDAPSettings = vi.mocked(updateLDAPSettings);
const mockNotificationsManager = vi.mocked(NotificationsManager);

describe("LDAPSettings", () => {
  beforeEach(() => {
    vi.resetAllMocks();
    mockUseAuthorized.mockReturnValue({ accessToken: "test-token" } as any);
    mockGetLDAPSettings.mockResolvedValue({ values: {} } as any);
    mockUpdateLDAPSettings.mockResolvedValue({ status: "success" } as any);
  });

  it("renders the LDAP settings card with title and description", () => {
    renderWithProviders(<LDAPSettings />);

    expect(screen.getByText("LDAP 登录设置")).toBeInTheDocument();
    expect(screen.getByText(/用户可使用 LDAP \/ Active Directory 账号密码登录 XHub/)).toBeInTheDocument();
  });

  it("renders all configured form fields", () => {
    renderWithProviders(<LDAPSettings />);

    expect(screen.getByLabelText("启用 LDAP 登录")).toBeInTheDocument();
    expect(screen.getByPlaceholderText("ldaps://ldap.example.com:636")).toBeInTheDocument();
    expect(screen.getByPlaceholderText("cn=readonly,dc=example,dc=com")).toBeInTheDocument();
    expect(screen.getByPlaceholderText("dc=example,dc=com")).toBeInTheDocument();
    expect(screen.getByPlaceholderText("(uid={username})")).toBeInTheDocument();
    expect(screen.getByPlaceholderText("mail")).toBeInTheDocument();
  });

  it("shows the fixed default role as 内部用户 (Create/Delete/View)", () => {
    renderWithProviders(<LDAPSettings />);

    expect(screen.getByText("内部用户（创建 / 删除 / 查看）")).toBeInTheDocument();
  });

  it("toggles the enabled switch", async () => {
    const user = userEvent.setup();
    renderWithProviders(<LDAPSettings />);

    const switchElement = screen.getByRole("switch", { name: "启用 LDAP 登录" });
    expect(switchElement).not.toBeChecked();

    await user.click(switchElement);

    await waitFor(() => {
      expect(switchElement).toBeChecked();
    });
  });

  it("loads existing settings into the form", async () => {
    mockGetLDAPSettings.mockResolvedValue({
      values: {
        enabled: true,
        server_url: "ldaps://corp.example.com:636",
        user_search_base: "dc=corp,dc=example,dc=com",
      },
    } as any);

    renderWithProviders(<LDAPSettings />);

    await waitFor(() => {
      expect(screen.getByPlaceholderText("ldaps://ldap.example.com:636")).toHaveValue("ldaps://corp.example.com:636");
    });
    expect(screen.getByRole("switch", { name: "启用 LDAP 登录" })).toBeChecked();
  });

  it("saves the form and shows a success notification", async () => {
    const user = userEvent.setup();
    mockUpdateLDAPSettings.mockImplementation(() => Promise.resolve({ status: "success" } as any));

    renderWithProviders(<LDAPSettings />);

    await waitFor(() => {
      expect(screen.getByPlaceholderText("ldaps://ldap.example.com:636")).not.toBeDisabled();
    });
    await user.type(screen.getByPlaceholderText("ldaps://ldap.example.com:636"), "ldaps://x.example.com");
    await user.type(screen.getByPlaceholderText("dc=example,dc=com"), "dc=x");

    await user.click(screen.getByRole("button", { name: "保存设置" }));

    await waitFor(() => {
      expect(mockUpdateLDAPSettings).toHaveBeenCalledWith(
        "test-token",
        expect.objectContaining({
          server_url: "ldaps://x.example.com",
          user_search_base: "dc=x",
        }),
      );
      expect(mockNotificationsManager.success).toHaveBeenCalledWith("LDAP 设置已保存");
    });
  });

  it("shows an error notification when the save fails", async () => {
    const user = userEvent.setup();
    mockUpdateLDAPSettings.mockImplementation(() => Promise.reject(new Error("save failed")));

    renderWithProviders(<LDAPSettings />);

    await waitFor(() => {
      expect(screen.getByPlaceholderText("ldaps://ldap.example.com:636")).not.toBeDisabled();
    });
    await user.type(screen.getByPlaceholderText("ldaps://ldap.example.com:636"), "ldaps://x.example.com");
    await user.type(screen.getByPlaceholderText("dc=example,dc=com"), "dc=x");

    await user.click(screen.getByRole("button", { name: "保存设置" }));

    await waitFor(() => {
      expect(mockNotificationsManager.error).toHaveBeenCalledWith("save failed");
    });
  });
});
