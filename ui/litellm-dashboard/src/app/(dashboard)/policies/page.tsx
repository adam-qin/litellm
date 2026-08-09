"use client";

import PoliciesPanel from "./_components";
import useAuthorized from "@/app/(dashboard)/hooks/useAuthorized";
import { isAdminRole } from "@/utils/roles";

export default function Policies() {
  const { accessToken, userRole } = useAuthorized();
  if (!isAdminRole(userRole)) {
    return <div className="p-6 text-sm text-muted-foreground">无权访问策略管理。</div>;
  }
  return <PoliciesPanel accessToken={accessToken} userRole={userRole} />;
}
