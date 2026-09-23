import type { ReactNode } from 'react';
import { useEffect, useMemo, useState } from 'react';
import { Button } from './button';

type Column<T> = {
  key: string;
  header: string;
  className?: string;
  render?: (row: T) => ReactNode;
  value?: (row: T) => ReactNode;
};

type DataTableProps<T> = {
  columns: Column<T>[];
  data: T[];
  rowKey: (row: T) => string;
  pageSize?: number;
  loading?: boolean;
  emptyTitle?: string;
  emptyDescription?: string;
  onRowClick?: (row: T) => void;
  className?: string;
  showPagination?: boolean;
};

export function DataTable<T>({
  columns,
  data,
  rowKey,
  pageSize = 10,
  loading = false,
  emptyTitle = 'No records',
  emptyDescription = 'There are no rows to display yet.',
  onRowClick,
  className = '',
  showPagination = true,
}: DataTableProps<T>) {
  const [page, setPage] = useState(1);
  const [rowsPerPage, setRowsPerPage] = useState(pageSize);

  useEffect(() => {
    setPage(1);
  }, [data.length, pageSize]);

  const totalPages = Math.max(1, Math.ceil(data.length / rowsPerPage));
  const visibleRows = useMemo(
    () => data.slice((page - 1) * rowsPerPage, page * rowsPerPage),
    [data, page, rowsPerPage],
  );

  useEffect(() => {
    if (page > totalPages) {
      setPage(totalPages);
    }
  }, [page, totalPages]);

  if (loading) {
    return (
      <div className={`overflow-hidden rounded-[var(--radius-lg,0.75rem)] border border-gray-200 bg-white dark:border-gray-700 dark:bg-gray-900 ${className}`}>
        <div className="animate-pulse space-y-3 p-4">
          <div className="h-10 w-full rounded bg-gray-100 dark:bg-gray-800" />
          <div className="h-10 w-full rounded bg-gray-100 dark:bg-gray-800" />
          <div className="h-10 w-full rounded bg-gray-100 dark:bg-gray-800" />
        </div>
      </div>
    );
  }

  if (!data.length) {
    return (
      <div className={`overflow-hidden rounded-[var(--radius-lg,0.75rem)] border border-gray-200 bg-gray-50 p-8 text-center dark:border-gray-700 dark:bg-gray-900 ${className}`}>
        <h3 className="text-base font-semibold text-gray-900 dark:text-gray-100">{emptyTitle}</h3>
        <p className="mt-2 text-sm text-gray-500 dark:text-gray-400">{emptyDescription}</p>
      </div>
    );
  }

  return (
    <div className={`overflow-hidden rounded-[var(--radius-lg,0.75rem)] border border-gray-200 bg-white dark:border-gray-700 dark:bg-gray-900 ${className}`}>
      <div className="overflow-x-auto max-h-[55vh]">
        <table className="w-full min-w-0 table-auto border-collapse text-sm">
          <thead className="sticky top-0 z-10 bg-gray-50/95 backdrop-blur-sm text-left text-xs font-semibold uppercase tracking-wide text-gray-500 dark:bg-gray-800/95 dark:text-gray-400">
            <tr className="border-b border-gray-200 dark:border-gray-700">
              {columns.map((column) => (
                <th key={column.key} className={`px-4 py-3 ${column.className ?? ''}`}>
                  {column.header}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100 dark:divide-gray-700">
            {visibleRows.map((row) => (
              <tr
                key={rowKey(row)}
                className={onRowClick ? 'cursor-pointer transition-colors hover:bg-gray-50 dark:hover:bg-gray-800/80' : 'transition-colors hover:bg-gray-50 dark:hover:bg-gray-800/80'}
                onClick={onRowClick ? () => onRowClick(row) : undefined}
              >
                {columns.map((column) => (
                  <td key={`${rowKey(row)}-${column.key}`} className={`px-4 py-3 align-top ${column.className ?? ''}`}>
                    {column.render ? column.render(row) : (column.value ? column.value(row) : null)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {showPagination && (
        <div className="flex flex-col gap-3 border-t border-gray-200 bg-white px-4 py-3 text-sm text-gray-600 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-300 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-center gap-3">
            <span>Showing {Math.min((page - 1) * rowsPerPage + 1, data.length)}–{Math.min(page * rowsPerPage, data.length)} of {data.length}</span>
            <label className="flex items-center gap-2 text-xs uppercase tracking-wide text-gray-500 dark:text-gray-400">
              Rows
              <select
                value={rowsPerPage}
                onChange={(event) => setRowsPerPage(Number(event.target.value))}
                className="rounded-[var(--radius-md,0.5rem)] border border-gray-300 bg-white px-2 py-1 text-xs text-gray-700 dark:border-gray-600 dark:bg-gray-800 dark:text-gray-200"
              >
                <option value={10}>10</option>
                <option value={25}>25</option>
                <option value={50}>50</option>
              </select>
            </label>
          </div>

          <div className="flex items-center gap-2">
            <Button type="button" variant="outline" size="sm" disabled={page === 1} onClick={() => setPage((current) => Math.max(1, current - 1))}>
              Previous
            </Button>
            <span className="px-2 text-xs uppercase tracking-wide text-gray-500 dark:text-gray-400">Page {page} of {totalPages}</span>
            <Button type="button" variant="outline" size="sm" disabled={page >= totalPages} onClick={() => setPage((current) => Math.min(totalPages, current + 1))}>
              Next
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
