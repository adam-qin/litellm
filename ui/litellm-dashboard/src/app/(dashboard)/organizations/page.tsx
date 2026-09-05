"use client";

import OrganizationsPanel from "./_components/OrganizationsPanel";
import useAuthorized from "@/app/(dashboard)/hooks/useAuthorized";

export default function OrganizationsPage() {
  const { accessToken, userRole } = useAuthorized();
  return <OrganizationsPanel userRole={userRole ?? ""} accessToken={accessToken} />;
}
