import { useOrganizations } from "@/app/(dashboard)/hooks/organizations/useOrganizations";
import useAuthorized from "@/app/(dashboard)/hooks/useAuthorized";
import { useHealthReadinessDetails } from "@/app/(dashboard)/hooks/healthReadiness/useHealthReadinessDetails";
import { useLogout } from "@/app/(dashboard)/hooks/useLogout";
import { getProxyBaseUrl } from "@/components/networking";
import { useTheme } from "@/contexts/ThemeContext";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarMenuSub,
  SidebarSeparator,
  sidebarMenuButtonVariants,
} from "@/components/ui/sidebar";
import {
  Activity,
  BarChart3,
  Bell,
  Boxes,
  ChevronRight,
  KeyRound,
  Network,
  Palette,
  PanelLeftClose,
  PanelLeftOpen,
  PlayCircle,
  Route,
  ScrollText,
  Settings as SettingsIcon,
  ShieldCheck,
  User,
  Users,
  Wallet,
} from "lucide-react";
import Link from "next/link";
import { useMemo, useState } from "react";
import { cn } from "@/lib/cva.config";
import {
  all_admin_roles,
  internalUserRoles,
  isAdminRole,
  rolesAllowedToViewWriteScopedPages,
  rolesWithWriteAccess,
} from "../utils/roles";
import NewBadge from "./common_components/NewBadge";
import type { Organization } from "./networking";
import SidebarAccountMenu from "./SidebarAccountMenu/SidebarAccountMenu";
import SidebarUsageCard from "./SidebarUsageCard";
import { MIGRATED_PAGES, migratedHref, legacyPageHref } from "@/utils/migratedPages";

const ICON = { strokeWidth: 1.75 } as const;

interface SidebarProps {
  setPage: (page: string) => void;
  defaultSelectedKey: string;
  collapsed?: boolean;
  onToggleCollapsed?: () => void;
  enabledPagesInternalUsers?: string[] | null;
}

interface MenuItem {
  key: string;
  page: string;
  label: string | React.ReactNode;
  roles?: string[];
  children?: MenuItem[];
  icon?: React.ReactNode;
}

interface MenuGroup {
  groupLabel: string;
  items: MenuItem[];
  roles?: string[];
}

// Menu groups organized by category - defined outside component for export.
// Shape (key/page/label/roles/children) is consumed by page_utils.ts; only the
// icons changed to lucide as part of the sidebar redesign.
const menuGroups: MenuGroup[] = [
  {
    groupLabel: "模型网关",
    items: [
      { key: "api-keys", page: "api-keys", label: "虚拟密钥", icon: <KeyRound {...ICON} /> },
      {
        key: "llm-playground",
        page: "llm-playground",
        label: "模型调试",
        icon: <PlayCircle {...ICON} />,
        roles: rolesWithWriteAccess,
      },
      {
        key: "models",
        page: "models",
        label: "模型与端点",
        icon: <Network {...ICON} />,
        roles: rolesAllowedToViewWriteScopedPages,
      },
    ],
  },
  {
    groupLabel: "可观测性",
    items: [
      {
        key: "new_usage",
        page: "new_usage",
        icon: <BarChart3 {...ICON} />,
        roles: [...all_admin_roles, ...internalUserRoles],
        label: "用量分析",
      },
      { key: "logs", page: "logs", label: "日志", icon: <Activity {...ICON} /> },
    ],
  },
  {
    groupLabel: "访问控制",
    items: [
      { key: "teams", page: "teams", label: "团队", icon: <Users {...ICON} /> },
      { key: "users", page: "users", label: "内部用户", icon: <User {...ICON} />, roles: all_admin_roles },
      {
        key: "access-groups",
        page: "access-groups",
        label: "访问组",
        icon: <Boxes {...ICON} />,
        roles: all_admin_roles,
      },
      { key: "budgets", page: "budgets", label: "预算", icon: <Wallet {...ICON} />, roles: all_admin_roles },
    ],
  },
  {
    groupLabel: "安全合规",
    items: [
      { key: "guardrails", page: "guardrails", label: "护栏", icon: <ShieldCheck {...ICON} /> },
      {
        key: "policies",
        page: "policies",
        label: "策略",
        icon: <ScrollText {...ICON} />,
        roles: all_admin_roles,
      },
    ],
  },
  {
    groupLabel: "系统设置",
    roles: all_admin_roles,
    items: [
      {
        key: "settings",
        page: "settings",
        label: (
          <span className="flex items-center gap-2">
            系统设置 <NewBadge />
          </span>
        ),
        icon: <SettingsIcon {...ICON} />,
        roles: all_admin_roles,
        children: [
          {
            key: "router-settings",
            page: "router-settings",
            label: "路由设置",
            icon: <Route {...ICON} />,
            roles: all_admin_roles,
          },
          {
            key: "logging-and-alerts",
            page: "logging-and-alerts",
            label: "日志与告警",
            icon: <Bell {...ICON} />,
            roles: all_admin_roles,
          },
          {
            key: "admin-panel",
            page: "admin-panel",
            label: (
              <span className="flex items-center gap-2">
                管理设置{" "}
                <NewBadge dot>
                  <span />
                </NewBadge>
              </span>
            ),
            icon: <SettingsIcon {...ICON} />,
            roles: all_admin_roles,
          },
          {
            key: "cost-tracking",
            page: "cost-tracking",
            label: "成本追踪",
            icon: <BarChart3 {...ICON} />,
            roles: all_admin_roles,
          },
          { key: "ui-theme", page: "ui-theme", label: "界面主题", icon: <Palette {...ICON} />, roles: all_admin_roles },
        ],
      },
    ],
  },
];

const findParentKey = (page: string): string | null => {
  for (const group of menuGroups) {
    for (const item of group.items) {
      if (item.children?.some((c) => c.page === page || c.key === page)) return item.key;
    }
  }
  return null;
};

const findMenuItemKey = (page: string): string => {
  for (const group of menuGroups) {
    for (const item of group.items) {
      if (item.page === page) return item.key;
      const child = item.children?.find((c) => c.page === page);
      if (child) return child.key;
    }
  }
  return "api-keys";
};

const labelText = (item: MenuItem): string => (typeof item.label === "string" ? item.label : item.key);

const SECTION_DISPLAY: Record<string, string> = {
  模型网关: "模型网关",
  可观测性: "可观测性",
  访问控制: "访问控制",
  安全合规: "安全合规",
  系统设置: "系统设置",
};

const prettify = (key: string): string =>
  key
    .split(/[-_]/)
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(" ");

// Breadcrumb ("Section" / "Page") for the top bar, derived from the same nav config.
export const getBreadcrumb = (page: string): { section: string | null; title: string } => {
  for (const group of menuGroups) {
    for (const item of group.items) {
      const section = SECTION_DISPLAY[group.groupLabel] ?? group.groupLabel;
      if (item.page === page)
        return { section, title: typeof item.label === "string" ? item.label : prettify(item.key) };
      const child = item.children?.find((c) => c.page === page);
      if (child) return { section, title: typeof child.label === "string" ? child.label : prettify(child.key) };
    }
  }
  return { section: null, title: prettify(page) };
};

const Sidebar_: React.FC<SidebarProps> = ({
  setPage,
  defaultSelectedKey,
  collapsed = false,
  onToggleCollapsed,
  enabledPagesInternalUsers,
}) => {
  const { userId, accessToken, userRole } = useAuthorized();
  const { data: organizations } = useOrganizations();
  const { logoUrl } = useTheme();
  const { data: healthData } = useHealthReadinessDetails(accessToken);
  const logout = useLogout(accessToken);

  const baseUrl = getProxyBaseUrl();
  const version = healthData?.litellm_version;
  const selectedKey = findMenuItemKey(defaultSelectedKey);

  const [openGroups, setOpenGroups] = useState<Set<string>>(() => {
    const parent = findParentKey(defaultSelectedKey);
    return new Set(parent ? [parent] : []);
  });

  // Keep the active page's parent group expanded as the user navigates, using the
  // "adjust state during render" pattern rather than an effect (avoids a
  // setState-in-effect render cascade).
  const [prevSelectedKey, setPrevSelectedKey] = useState(defaultSelectedKey);
  if (defaultSelectedKey !== prevSelectedKey) {
    setPrevSelectedKey(defaultSelectedKey);
    const parent = findParentKey(defaultSelectedKey);
    if (parent && !openGroups.has(parent)) {
      setOpenGroups((prev) => new Set(prev).add(parent));
    }
  }

  const isOrgAdmin = useMemo(() => {
    if (!userId || !organizations) return false;
    return organizations.some((org: Organization) =>
      org.members?.some((member) => member.user_id === userId && member.user_role === "org_admin"),
    );
  }, [userId, organizations]);

  const filterItemsByRole = (items: MenuItem[]): MenuItem[] => {
    const isAdmin = isAdminRole(userRole);
    return items
      .map((item) => ({ ...item, children: item.children ? filterItemsByRole(item.children) : undefined }))
      .filter((item) => {
        if (item.children && item.children.length === 0) return false;
        if (item.key === "users") {
          const hasRoleAccess = !item.roles || item.roles.includes(userRole) || isOrgAdmin;
          if (!hasRoleAccess) return false;
          if (!isAdmin && enabledPagesInternalUsers != null) return enabledPagesInternalUsers.includes(item.page);
          return true;
        }
        if (item.roles && !item.roles.includes(userRole)) return false;
        if (!isAdmin && enabledPagesInternalUsers != null) {
          if (item.children && item.children.length > 0) {
            const hasVisibleChildren = item.children.some((child) => enabledPagesInternalUsers.includes(child.page));
            if (hasVisibleChildren) return true;
          }
          return enabledPagesInternalUsers.includes(item.page);
        }
        return true;
      });
  };

  const visibleGroups = menuGroups
    .filter((group) => !group.roles || group.roles.includes(userRole))
    .map((group) => ({ groupLabel: group.groupLabel, items: filterItemsByRole(group.items) }))
    .filter((group) => group.items.length > 0);

  const toggleGroup = (key: string) => {
    if (collapsed) {
      onToggleCollapsed?.();
      setOpenGroups((prev) => new Set(prev).add(key));
      return;
    }
    setOpenGroups((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  };

  const handleLeafClick = (e: React.MouseEvent, item: MenuItem) => {
    if (e.metaKey || e.ctrlKey) return;
    if (e.shiftKey || e.button === 1) return;
    e.preventDefault();
    setPage(item.page);
  };

  const renderLeaf = (item: MenuItem, isChild: boolean) => {
    const active = selectedKey === item.key;
    const size = isChild ? "sub" : "default";
    const label = <span className="flex-1 truncate group-data-[collapsed=true]/sidebar:hidden">{item.label}</span>;

    const href = MIGRATED_PAGES[item.page] ? migratedHref(MIGRATED_PAGES[item.page]) : legacyPageHref(item.page);
    return (
      <a
        key={item.key}
        href={href}
        onClick={(e) => handleLeafClick(e, item)}
        title={collapsed ? labelText(item) : undefined}
        data-active={active || undefined}
        className={cn(sidebarMenuButtonVariants({ isActive: active, size }))}
      >
        {item.icon}
        {label}
      </a>
    );
  };

  const renderItem = (item: MenuItem) => {
    const isGroup = !!item.children && item.children.length > 0;
    if (!isGroup) {
      return <SidebarMenuItem key={item.key}>{renderLeaf(item, false)}</SidebarMenuItem>;
    }

    const active = selectedKey === item.key;
    const open = openGroups.has(item.key);
    return (
      <SidebarMenuItem key={item.key}>
        <SidebarMenuButton
          isActive={active}
          onClick={() => toggleGroup(item.key)}
          title={collapsed ? labelText(item) : undefined}
        >
          {item.icon}
          <span className="flex-1 truncate group-data-[collapsed=true]/sidebar:hidden">{item.label}</span>
          <ChevronRight
            className={cn(
              "size-4 shrink-0 transition-transform group-data-[collapsed=true]/sidebar:hidden",
              open && "rotate-90",
            )}
          />
        </SidebarMenuButton>
        {open && (
          <SidebarMenuSub>
            {item.children!.map((child) => (
              <SidebarMenuItem key={child.key}>{renderLeaf(child, true)}</SidebarMenuItem>
            ))}
          </SidebarMenuSub>
        )}
      </SidebarMenuItem>
    );
  };

  const logoSrc = logoUrl || `${baseUrl}/get_image`;

  return (
    <Sidebar collapsed={collapsed}>
      <SidebarHeader className="h-14 border-b border-border group-data-[collapsed=true]/sidebar:h-auto">
        <div className="flex items-center justify-between gap-2 group-data-[collapsed=true]/sidebar:flex-col">
          <div className="flex min-w-0 items-center gap-2">
            <Link href={baseUrl || "/"} className="flex min-w-0 items-center" aria-label="XHub home">
              <img
                src={logoSrc}
                alt="XHub"
                className="h-7 w-auto max-w-[150px] object-contain group-data-[collapsed=true]/sidebar:w-7"
              />
            </Link>
            {version && (
              <Badge
                variant="outline"
                className="px-1.5 py-0 font-mono text-[10px] font-medium text-muted-foreground group-data-[collapsed=true]/sidebar:hidden"
              >
                v{version}
              </Badge>
            )}
          </div>
          {onToggleCollapsed && (
            <Button
              variant="ghost"
              size="icon-sm"
              onClick={onToggleCollapsed}
              aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
              className="flex-none text-muted-foreground"
            >
              {collapsed ? <PanelLeftOpen /> : <PanelLeftClose />}
            </Button>
          )}
        </div>
      </SidebarHeader>

      <SidebarContent>
        {visibleGroups.map((group, gi) => (
          <SidebarGroup key={group.groupLabel}>
            {gi > 0 && <SidebarSeparator className="hidden group-data-[collapsed=true]/sidebar:block" />}
            <SidebarGroupLabel>{group.groupLabel}</SidebarGroupLabel>
            <SidebarMenu>{group.items.map((item) => renderItem(item))}</SidebarMenu>
          </SidebarGroup>
        ))}
      </SidebarContent>

      <SidebarFooter>
        {isAdminRole(userRole) && (
          <SidebarUsageCard
            accessToken={accessToken}
            collapsed={collapsed}
            onExpandRail={() => onToggleCollapsed?.()}
          />
        )}
        <SidebarAccountMenu onLogout={logout} collapsed={collapsed} />
      </SidebarFooter>
    </Sidebar>
  );
};

export default Sidebar_;

export { menuGroups };
