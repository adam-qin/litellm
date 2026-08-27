"use client";

import Sidebar from "@/components/leftnav";
import { getUISettings } from "@/components/networking";
import useAuthorized from "@/app/(dashboard)/hooks/useAuthorized";
import { useEffect, useState } from "react";

interface SidebarProviderProps {
  setPage: (page: string) => void;
  defaultSelectedKey: string;
  sidebarCollapsed: boolean;
  onToggleCollapsed?: () => void;
}

const SidebarProvider = ({
  setPage,
  defaultSelectedKey,
  sidebarCollapsed,
  onToggleCollapsed,
}: SidebarProviderProps) => {
  const { accessToken } = useAuthorized();
  const [enabledPagesInternalUsers, setEnabledPagesInternalUsers] = useState<string[] | null>(null);
  const [isTeamScopedInstance, setIsTeamScopedInstance] = useState(false);

  useEffect(() => {
    const fetchUISettings = async () => {
      if (!accessToken) {
        return;
      }

      try {
        const settings = await getUISettings(accessToken);

        // API returns 'values' not 'settings'. Capability fields are
        // top-level and intentionally separate from persisted UI settings.
        if (settings?.values?.enabled_ui_pages_internal_users !== undefined) {
          setEnabledPagesInternalUsers(settings.values.enabled_ui_pages_internal_users);
        }
        setIsTeamScopedInstance(settings?.is_team_scoped_instance === true);
      } catch (error) {
        console.error("[SidebarProvider] Failed to fetch UI settings:", error);
      }
    };

    fetchUISettings();
  }, [accessToken]);

  return (
    <Sidebar
      setPage={setPage}
      defaultSelectedKey={defaultSelectedKey}
      collapsed={sidebarCollapsed}
      onToggleCollapsed={onToggleCollapsed}
      enabledPagesInternalUsers={enabledPagesInternalUsers}
      isTeamScopedInstance={isTeamScopedInstance}
    />
  );
};

export default SidebarProvider;
