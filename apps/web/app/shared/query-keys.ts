import type {
  AdminDatasetRowsQuery,
  AdminEntityKind,
  AdminEntityListQuery,
  AdminUserListQuery,
} from "../admin/api";

export const queryKeys = {
  public: {
    festivalMonthly: (year: number, month: number) =>
      ["public", "festivals", "monthly", year, month] as const,
  },
  admin: {
    root: () => ["admin"] as const,
    me: () => ["admin", "me"] as const,
    datasets: () => ["admin", "datasets"] as const,
    datasetRowsRoot: () => ["admin", "datasets", "rows"] as const,
    datasetRows: (tableName: string, query: AdminDatasetRowsQuery) =>
      [
        "admin",
        "datasets",
        "rows",
        tableName,
        query.page,
        query.limit,
        query.search,
        query.sortBy,
        query.sortDir,
        query.filter.column,
        query.filter.value,
      ] as const,
    usersRoot: () => ["admin", "users"] as const,
    users: (query: AdminUserListQuery) =>
      [
        "admin",
        "users",
        query.page,
        query.limit,
        query.search,
        query.accountStatus,
        query.systemRole,
      ] as const,
    entitiesRoot: () => ["admin", "entities"] as const,
    entityList: (entity: AdminEntityKind, query: AdminEntityListQuery) =>
      [
        "admin",
        "entities",
        entity,
        query.page,
        query.limit,
        query.search,
        JSON.stringify(query.filters),
      ] as const,
    entityDetail: (entity: AdminEntityKind, itemId: string) =>
      ["admin", "entities", entity, itemId] as const,
  },
};
