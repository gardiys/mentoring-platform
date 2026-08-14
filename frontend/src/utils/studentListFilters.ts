import type {
  MentorStudentSort,
  StudentAccessFilter,
  StudentLearningStatus,
} from "../types/api";

export const STUDENT_PROGRESS_FILTERS_STORAGE_KEY =
  "mentoring-platform:student-progress-filters:v1";
export const ADMIN_STUDENTS_FILTERS_STORAGE_KEY =
  "mentoring-platform:admin-students-filters:v1";

export interface StoredStudentListFilters {
  search: string;
  trackId: string | null;
  statuses: StudentLearningStatus[];
  access: StudentAccessFilter;
  mentorFilter: string;
  sort: MentorStudentSort;
}

const defaultFilters: StoredStudentListFilters = {
  search: "",
  trackId: null,
  statuses: [],
  access: "active",
  mentorFilter: "all",
  sort: "name_asc",
};
const learningStatuses: StudentLearningStatus[] = [
  "learning",
  "interviewing",
  "probation",
  "finished",
];
const accessFilters: StudentAccessFilter[] = ["active", "blocked", "all"];
const studentSorts: MentorStudentSort[] = [
  "name_asc",
  "learning_start_desc",
  "learning_start_asc",
  "last_activity_desc",
  "last_activity_asc",
];

export function readStoredStudentListFilters(
  storageKey: string,
): StoredStudentListFilters {
  try {
    const raw = window.localStorage.getItem(storageKey);
    if (!raw) return defaultFilters;
    const stored = JSON.parse(raw) as Record<string, unknown>;
    const statuses = Array.isArray(stored.statuses)
      ? [
          ...new Set(
            stored.statuses.filter(
              (status): status is StudentLearningStatus =>
                typeof status === "string" &&
                learningStatuses.includes(status as StudentLearningStatus),
            ),
          ),
        ]
      : [];
    const access = accessFilters.includes(stored.access as StudentAccessFilter)
      ? (stored.access as StudentAccessFilter)
      : defaultFilters.access;
    return {
      search: typeof stored.search === "string" ? stored.search : "",
      trackId: typeof stored.trackId === "string" ? stored.trackId : null,
      statuses,
      access,
      mentorFilter:
        typeof stored.mentorFilter === "string" && stored.mentorFilter
          ? stored.mentorFilter
          : "all",
      sort: studentSorts.includes(stored.sort as MentorStudentSort)
        ? (stored.sort as MentorStudentSort)
        : defaultFilters.sort,
    };
  } catch {
    return defaultFilters;
  }
}

export function storeStudentListFilters(
  storageKey: string,
  filters: StoredStudentListFilters,
) {
  try {
    window.localStorage.setItem(storageKey, JSON.stringify(filters));
  } catch {
    // Some browsers can disable localStorage in private or restricted modes.
  }
}
