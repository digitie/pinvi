"use client";

import { create } from "zustand";
import type { AdminDatasetColumn, AdminDatasetSummary } from "../admin/api";

type SortDir = "asc" | "desc";

export type SubmittedFilter = {
  column: string;
  value: string;
};

type LoginPageState = {
  email: string;
  password: string;
  year: number;
  selectedMonth: number;
  loginMessage: string | null;
  setLoginField: (field: "email" | "password", value: string) => void;
  setSelectedMonth: (month: number) => void;
  setLoginMessage: (message: string | null) => void;
  clearLoginFeedback: () => void;
  resetLoginPassword: () => void;
};

const initialLoginDate = getKstYearMonth();

export const useLoginPageStore = create<LoginPageState>((set) => ({
  email: "",
  password: "",
  year: initialLoginDate.year,
  selectedMonth: initialLoginDate.month,
  loginMessage: null,
  setLoginField: (field, value) => set(field === "email" ? { email: value } : { password: value }),
  setSelectedMonth: (month) => set({ selectedMonth: month }),
  setLoginMessage: (message) => set({ loginMessage: message }),
  clearLoginFeedback: () => set({ loginMessage: null }),
  resetLoginPassword: () => set({ password: "" }),
}));

type SignupPageState = {
  email: string;
  password: string;
  nickname: string;
  name: string;
  birthYearMonth: string;
  gender: string;
  residenceSigunguCode: string;
  setSignupField: (
    field:
      | "email"
      | "password"
      | "nickname"
      | "name"
      | "birthYearMonth"
      | "gender"
      | "residenceSigunguCode",
    value: string,
  ) => void;
  resetSignupPassword: () => void;
};

export const useSignupPageStore = create<SignupPageState>((set) => ({
  email: "",
  password: "",
  nickname: "",
  name: "",
  birthYearMonth: "",
  gender: "",
  residenceSigunguCode: "",
  setSignupField: (field, value) => {
    switch (field) {
      case "birthYearMonth":
        set({ birthYearMonth: value });
        break;
      case "email":
        set({ email: value });
        break;
      case "gender":
        set({ gender: value });
        break;
      case "name":
        set({ name: value });
        break;
      case "nickname":
        set({ nickname: value });
        break;
      case "password":
        set({ password: value });
        break;
      case "residenceSigunguCode":
        set({ residenceSigunguCode: value });
        break;
    }
  },
  resetSignupPassword: () => set({ password: "" }),
}));

type AdminLoginState = {
  email: string;
  password: string;
  setAdminLoginField: (field: "email" | "password", value: string) => void;
  resetAdminLoginPassword: () => void;
};

export const useAdminLoginStore = create<AdminLoginState>((set) => ({
  email: "admin@ad.min",
  password: "admin",
  setAdminLoginField: (field, value) =>
    set(field === "email" ? { email: value } : { password: value }),
  resetAdminLoginPassword: () => set({ password: "" }),
}));

type AdminDataBrowserState = {
  datasetSearch: string;
  filterColumn: string;
  filterValue: string;
  limit: number;
  page: number;
  search: string;
  selectedTable: string;
  sortBy: string;
  sortDir: SortDir;
  submittedFilter: SubmittedFilter;
  submittedSearch: string;
  applySearchAndFilter: () => void;
  changeSort: (column: AdminDatasetColumn) => void;
  initializeDatasetSelection: (dataset: AdminDatasetSummary | null, defaultPageSize: number) => void;
  selectDataset: (dataset: AdminDatasetSummary | null) => void;
  setDatasetSearch: (datasetSearch: string) => void;
  setFilterColumn: (filterColumn: string) => void;
  setFilterValue: (filterValue: string) => void;
  setLimit: (limit: number) => void;
  setPage: (page: number) => void;
  setSearch: (search: string) => void;
  setSortBy: (sortBy: string) => void;
  setSortDir: (sortDir: SortDir) => void;
};

export const useAdminDataBrowserStore = create<AdminDataBrowserState>((set, get) => ({
  datasetSearch: "",
  filterColumn: "",
  filterValue: "",
  limit: 100,
  page: 1,
  search: "",
  selectedTable: "",
  sortBy: "",
  sortDir: "desc",
  submittedFilter: { column: "", value: "" },
  submittedSearch: "",
  applySearchAndFilter: () =>
    set((state) => ({
      page: 1,
      submittedFilter: {
        column: state.filterColumn,
        value: state.filterValue,
      },
      submittedSearch: state.search,
    })),
  changeSort: (column) => {
    if (!column.sortable) {
      return;
    }

    set((state) => ({
      page: 1,
      sortBy: column.name,
      sortDir: state.sortBy === column.name && state.sortDir === "asc" ? "desc" : "asc",
    }));
  },
  initializeDatasetSelection: (dataset, defaultPageSize) => {
    const state = get();
    if (state.selectedTable || !dataset) {
      return;
    }

    set({
      ...getDatasetSelectionState(dataset),
      limit: defaultPageSize,
    });
  },
  selectDataset: (dataset) => set(getDatasetSelectionState(dataset)),
  setDatasetSearch: (datasetSearch) => set({ datasetSearch }),
  setFilterColumn: (filterColumn) => set({ filterColumn }),
  setFilterValue: (filterValue) => set({ filterValue }),
  setLimit: (limit) => set({ limit, page: 1 }),
  setPage: (page) => set({ page }),
  setSearch: (search) => set({ search }),
  setSortBy: (sortBy) => set({ sortBy, page: 1 }),
  setSortDir: (sortDir) => set({ sortDir, page: 1 }),
}));

type AdminUsersState = {
  accountStatus: string;
  limit: number;
  page: number;
  search: string;
  submittedAccountStatus: string;
  submittedSearch: string;
  submittedSystemRole: string;
  systemRole: string;
  applyFilters: () => void;
  setAccountStatus: (accountStatus: string) => void;
  setLimit: (limit: number) => void;
  setPage: (page: number) => void;
  setSearch: (search: string) => void;
  setSystemRole: (systemRole: string) => void;
};

export const useAdminUsersStore = create<AdminUsersState>((set) => ({
  accountStatus: "",
  limit: 50,
  page: 1,
  search: "",
  submittedAccountStatus: "",
  submittedSearch: "",
  submittedSystemRole: "",
  systemRole: "",
  applyFilters: () =>
    set((state) => ({
      page: 1,
      submittedAccountStatus: state.accountStatus,
      submittedSearch: state.search,
      submittedSystemRole: state.systemRole,
    })),
  setAccountStatus: (accountStatus) => set({ accountStatus }),
  setLimit: (limit) => set({ limit, page: 1 }),
  setPage: (page) => set({ page }),
  setSearch: (search) => set({ search }),
  setSystemRole: (systemRole) => set({ systemRole }),
}));

function getDatasetSelectionState(dataset: AdminDatasetSummary | null) {
  return {
    filterColumn: dataset?.columns.find((column) => column.filterable)?.name ?? "",
    filterValue: "",
    page: 1,
    search: "",
    selectedTable: dataset?.table_name ?? "",
    sortBy: dataset?.columns.find((column) => column.sortable)?.name ?? "",
    sortDir: "desc" as const,
    submittedFilter: { column: "", value: "" },
    submittedSearch: "",
  };
}

function getKstYearMonth(): { year: number; month: number } {
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone: "Asia/Seoul",
    year: "numeric",
    month: "numeric",
  }).formatToParts(new Date());
  const year = Number(parts.find((part) => part.type === "year")?.value ?? "2026");
  const month = Number(parts.find((part) => part.type === "month")?.value ?? "1");
  return { year, month };
}
