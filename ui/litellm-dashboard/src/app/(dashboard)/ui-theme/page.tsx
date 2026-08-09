"use client";

import UIThemeSettings from "./UIThemeSettings";
import useAuthorized from "@/app/(dashboard)/hooks/useAuthorized";
import { isWritableAdminRole } from "@/utils/roles";

export default function UITheme() {
  const { accessToken, userRole, userId } = useAuthorized();
  if (!isWritableAdminRole(userRole)) {
    return <div className="p-6 text-sm text-muted-foreground">无权修改界面主题。</div>;
  }
  return <UIThemeSettings userID={userId} userRole={userRole} accessToken={accessToken} />;
}
