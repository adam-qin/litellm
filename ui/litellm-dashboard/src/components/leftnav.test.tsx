import { screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { renderWithProviders } from "../../tests/test-utils";
import { ThemeProvider } from "@/contexts/ThemeContext";
import Sidebar, { menuGroups, getBreadcrumb, getVisibleMenuGroups } from "./leftnav";

const { authState, mockUseAuthorized, mockUseOrganizations } = vi.hoisted(() => ({
  authState: {
    userId: "test-user-id",
    accessToken: "test-access-token",
    userRole: "Admin",
    token: "test-token",
    userEmail: "test@example.com",
    premiumUser: false,
    disabledPersonalKeyCreation: false,
    showSSOBanner: false,
  },
  mockUseAuthorized: vi.fn(),
  mockUseOrganizations: vi.fn(() => ({ data: [], isLoading: false, error: null })),
}));

vi.mock("@/app/(dashboard)/hooks/useAuthorized.ts", () => ({
  default: mockUseAuthorized,
}));

vi.mock("@/app/(dashboard)/hooks/organizations/useOrganizations", () => ({
  useOrganizations: mockUseOrganizations,
}));

// Version tag + logout target come from network hooks; keep them inert in unit tests.
vi.mock("@/app/(dashboard)/hooks/healthReadiness/useHealthReadinessDetails", () => ({
  useHealthReadinessDetails: () => ({ data: undefined }),
}));
vi.mock("@/app/(dashboard)/hooks/useLogout", () => ({
  useLogout: () => vi.fn(),
}));

const collectNavKeys = (): string[] =>
  menuGroups.flatMap((group) => group.items.flatMap((item) => [item.key, ...(item.children ?? []).map((c) => c.key)]));

describe("Sidebar (leftnav)", () => {
  it("filters menu groups according to the supplied role", () => {
    const labels = (role: string, isOrgAdmin = false) =>
      getVisibleMenuGroups(role, isOrgAdmin).flatMap((group) =>
        group.items.map((item) => (typeof item.label === "string" ? item.label : item.key)),
      );

    expect(labels("Admin")).toContain("模型调试");
    expect(labels("Admin Viewer")).not.toContain("模型调试");
    expect(labels("Admin Viewer")).toContain("模型与端点");
    expect(labels("Internal User")).toContain("护栏");
    expect(labels("Internal User")).not.toContain("策略");
    expect(labels("Org Admin", true)).toContain("内部用户");
  });

  const adminAuth = {
    userId: "test-user-id",
    accessToken: "test-access-token",
    userRole: "Admin",
    token: "test-token",
    userEmail: "test@example.com",
    premiumUser: false,
    disabledPersonalKeyCreation: false,
    showSSOBanner: false,
  };
  const defaultProps = {
    setPage: vi.fn(),
    defaultSelectedKey: "api-keys",
    collapsed: false,
  };
  const renderSidebar = (props = defaultProps) =>
    renderWithProviders(
      <ThemeProvider>
        <Sidebar {...props} />
      </ThemeProvider>,
    );

  beforeEach(() => {
    Object.assign(authState, adminAuth);
    mockUseAuthorized.mockReset();
    mockUseAuthorized.mockReturnValue(authState);
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => ({ values: {} }) }));
    mockUseOrganizations.mockReset();
    mockUseOrganizations.mockImplementation(() => ({ data: [], isLoading: false, error: null }));
  });

  it("defines all top-level (non-nested) tabs for admin", () => {
    const topLevelLabels = [
      "虚拟密钥",
      "模型调试",
      "模型与端点",
      "用量分析",
      "日志",
      "团队",
      "内部用户",
      "组织",
      "访问组",
      "预算",
      "护栏",
      "策略",
      "系统设置",
    ];

    const visibleLabels = getVisibleMenuGroups("Admin", false).flatMap((group) =>
      group.items.map((item) => (typeof item.label === "string" ? item.label : item.key)),
    );
    topLevelLabels.forEach((label) => expect(visibleLabels).toContain(label === "系统设置" ? "settings" : label));
  });

  it("does not render non-core product menus", () => {
    renderSidebar();

    [
      "Agentic",
      "MCP Servers",
      "Skills",
      "AI Hub",
      "Learning Resources",
      "Experimental",
      "Policies",
      "Developer Tools",
      "API Reference",
      "Chat",
      "Tools",
      "Guardrails Monitor",
      "Projects",
    ].forEach((label) => expect(screen.queryByText(label)).not.toBeInTheDocument());
  });

  it("has no duplicate keys among all menu items and their children", () => {
    // React keys must be unique across the whole nav config, otherwise the
    // active-item highlight and group expansion collide.
    const keys = collectNavKeys();
    const duplicates = keys.filter((key, i) => keys.indexOf(key) !== i);
    expect(duplicates).toEqual([]);
  });

  describe("Admin Viewer parity", () => {
    // Admin Viewer follows a "read parity with Proxy Admin, no writes, no
    // cost-incurring actions" rule. Playground stays hidden (incurs LLM
    // cost), while Models + Endpoints remains visible read-only.
    const adminViewerAuth = {
      userId: "admin-viewer-user-id",
      accessToken: "test-access-token",
      userRole: "Admin Viewer",
      token: "test-token",
      userEmail: "viewer@example.com",
      premiumUser: false,
      disabledPersonalKeyCreation: false,
      showSSOBanner: false,
    };

    it("hides Playground from Admin Viewer (cost-incurring action)", () => {
      Object.assign(authState, adminViewerAuth);
      renderSidebar();
      expect(screen.queryByText("模型调试")).not.toBeInTheDocument();
    });

    it("shows Models + Endpoints to Admin Viewer (read-only)", () => {
      const visibleLabels = getVisibleMenuGroups(adminViewerAuth.userRole, false).flatMap((group) =>
        group.items.map((item) => (typeof item.label === "string" ? item.label : item.key)),
      );
      expect(visibleLabels).toContain("模型与端点");
    });

    it("shows Logs to Admin Viewer", () => {
      Object.assign(authState, adminViewerAuth);
      renderSidebar();
      expect(screen.getByText("日志")).toBeInTheDocument();
    });
  });

  it("preserves the original Guardrails and Policies role visibility", () => {
    Object.assign(authState, {
      userId: "internal-user-id",
      accessToken: "test-access-token",
      userRole: "Internal User",
      token: "test-token",
      userEmail: "internal@example.com",
      premiumUser: false,
      disabledPersonalKeyCreation: false,
      showSSOBanner: false,
    });

    renderSidebar();

    expect(screen.getByText("护栏")).toBeInTheDocument();
    expect(screen.queryByText("策略")).not.toBeInTheDocument();
  });

  it("shows Internal Users and Organizations for organization admins", () => {
    Object.assign(authState, {
      userId: "org-admin-user-id",
      accessToken: "test-access-token",
      userRole: "Org Admin",
      token: "test-token",
      userEmail: "orgadmin@example.com",
      premiumUser: false,
      disabledPersonalKeyCreation: false,
      showSSOBanner: false,
    });

    mockUseOrganizations.mockReturnValueOnce({
      data: [
        {
          organization_id: "org-1",
          organization_name: "Test Organization",
          spend: 0,
          max_budget: null,
          models: [],
          tpm_limit: null,
          rpm_limit: null,
          members: [
            {
              user_id: "org-admin-user-id",
              user_role: "org_admin",
            },
          ],
        },
      ],
      isLoading: false,
      error: null,
    } as any);

    const visibleLabels = getVisibleMenuGroups("Org Admin", true).flatMap((group) =>
      group.items.map((item) => (typeof item.label === "string" ? item.label : item.key)),
    );
    expect(visibleLabels).toContain("内部用户");
    expect(visibleLabels).toContain("组织");
  });

  it("marks the selected page's nav item active", () => {
    renderSidebar({ ...defaultProps, defaultSelectedKey: "logs" });
    const logs = screen.getByText("日志").closest("a");
    expect(logs).toHaveAttribute("data-active", "true");
    // A different item must not be active.
    expect(screen.getByText("虚拟密钥").closest("a")).not.toHaveAttribute("data-active");
  });

  it("hides labels but keeps items reachable (icon + link) when collapsed to the rail", () => {
    const { container } = renderSidebar({ ...defaultProps, collapsed: true });
    expect(container.querySelector('[data-slot="sidebar"]')).toHaveAttribute("data-collapsed", "true");
    // The item stays navigable in the icon-only rail: its link still renders with
    // an icon (asserting the <a> + svg, not the text, so a removed icon would
    // fail here), while the label is present but CSS-hidden.
    const label = screen.getByText("虚拟密钥");
    const link = label.closest("a");
    expect(link).not.toBeNull();
    expect(link!.querySelector("svg")).not.toBeNull();
    expect(label).toHaveClass("group-data-[collapsed=true]/sidebar:hidden");
  });
});

describe("getBreadcrumb", () => {
  it("resolves a top-level page to its section + title", () => {
    expect(getBreadcrumb("api-keys")).toEqual({ section: "模型网关", title: "虚拟密钥" });
    expect(getBreadcrumb("logs")).toEqual({ section: "可观测性", title: "日志" });
  });

  it("resolves a nested child page to its parent section", () => {
    expect(getBreadcrumb("router-settings")).toEqual({ section: "系统设置", title: "路由设置" });
  });

  it("falls back to a prettified title with no section for unknown pages", () => {
    expect(getBreadcrumb("some-unknown-page")).toEqual({ section: null, title: "Some Unknown Page" });
  });
});
