import { useCallback, useState } from "react";
import { useQuery, keepPreviousData } from "@tanstack/react-query";
import { ColumnFiltersState, OnChangeFn, PaginationState } from "@tanstack/react-table";
import { uiAuditLogsCall } from "../networking";
import { AuditLogEntry } from "./AuditLogsTableColumns";
import { AuditLogsTable } from "./AuditLogsTable";
import { AuditLogDrawer } from "./AuditLogDrawer/AuditLogDrawer";

interface AuditLogsProps {
  accessToken: string | null;
  token: string | null;
  userRole: string | null;
  userID: string | null;
  isActive: boolean;
}

const PAGE_SIZE = 50;

interface AuditLogsResponse {
  audit_logs: AuditLogEntry[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

export default function AuditLogsPanel({
  userID,
  userRole,
  token,
  accessToken,
  isActive,
}: AuditLogsProps) {
  const [pagination, setPagination] = useState<PaginationState>({ pageIndex: 0, pageSize: PAGE_SIZE });
  const [columnFilters, setColumnFilters] = useState<ColumnFiltersState>([]);
  const [selectedLog, setSelectedLog] = useState<AuditLogEntry | null>(null);
  const [drawerOpen, setDrawerOpen] = useState(false);

  const getFilterValue = (columnId: string): string | undefined => {
    const entry = columnFilters.find((filter) => filter.id === columnId);
    return typeof entry?.value === "string" && entry.value.trim() ? entry.value.trim() : undefined;
  };

  const canQueryAuditLogs = !!accessToken && !!token && !!userRole && !!userID && isActive;

  const query = useQuery<AuditLogsResponse>({
    queryKey: ["audit_logs", pagination.pageIndex, pagination.pageSize, columnFilters],
    queryFn: async () => {
      if (!accessToken) {
        return { audit_logs: [], total: 0, page: 1, page_size: pagination.pageSize, total_pages: 0 };
      }
      return uiAuditLogsCall({
        accessToken,
        page: pagination.pageIndex + 1,
        page_size: pagination.pageSize,
        params: {
          object_id: getFilterValue("object_id"),
          changed_by: getFilterValue("changed_by"),
          object_key_hash: getFilterValue("key_hash"),
          object_team_id: getFilterValue("team_id"),
          action: getFilterValue("action"),
          table_name: getFilterValue("table_name"),
          sort_by: "updated_at",
          sort_order: "desc",
        },
      });
    },
    enabled: canQueryAuditLogs,
    placeholderData: keepPreviousData,
  });

  const handleColumnFiltersChange = useCallback<OnChangeFn<ColumnFiltersState>>((updaterOrValue) => {
    setColumnFilters(updaterOrValue);
    setPagination((prev) => ({ ...prev, pageIndex: 0 }));
  }, []);

  const handleViewLog = useCallback((log: AuditLogEntry) => {
    setSelectedLog(log);
    setDrawerOpen(true);
  }, []);

  return (
    <>
      <div className="flex items-center justify-between mb-4">
        <h1 className="text-xl font-semibold">Audit Logs</h1>
      </div>

      <AuditLogsTable
        data={query.data?.audit_logs ?? []}
        rowCount={query.data?.total ?? 0}
        isLoading={query.isLoading}
        isRefreshing={query.isFetching}
        pagination={pagination}
        onPaginationChange={setPagination}
        columnFilters={columnFilters}
        onColumnFiltersChange={handleColumnFiltersChange}
        onRefresh={() => query.refetch()}
        onViewLog={handleViewLog}
      />

      <AuditLogDrawer open={drawerOpen} onClose={() => setDrawerOpen(false)} log={selectedLog} />
    </>
  );
}
