import type {
  AdminKnowledgeTopicMutation,
  AdminKnowledgeEntryMutation,
  AdminKnowledgeEntryRead,
  AdminKnowledgeTopicOutline,
  AdminKnowledgeTopicRead,
  AdminKnowledgeTopicSettingsMutation,
  AdminKnowledgeTopicSummary,
  AdminInterviewCardMutation,
  AdminInterviewCardPage,
  AdminInterviewCardRead,
  AdminInterviewDeckMutation,
  AdminInterviewDeckRead,
  AdminInterviewDeckSettingsMutation,
  AdminInterviewDeckSummary,
  AdminRoadmapCreate,
  AdminRoadmapOutline,
  AdminRoadmapRead,
  AdminRoadmapSettingsMutation,
  AdminRoadmapSummary,
  AdminRoadmapUpdate,
  AdminSectionMutation,
  AdminSectionOutline,
  AdminTopicCreate,
  AdminTopicRead,
  AdminTrackMutation,
  AdminTrackOptions,
  AdminTrackRead,
  KnowledgeEntryDetail,
  KnowledgeSearchResult,
  KnowledgeTopicDetail,
  KnowledgeTopicListItem,
  InterviewDeckListItem,
  InterviewReviewRating,
  InterviewReviewResult,
  InterviewStudySession,
  InterviewTopicOption,
  MentorStudentDetail,
  MentorStudentListItem,
  ProgressStatus,
  ProgressUpdateResponse,
  RoadmapDetail,
  RoadmapListItem,
  TopicDetail,
  User,
} from "../types/api";
import { apiRequest } from "./client";

export const api = {
  me: () => apiRequest<User>("/api/v1/me"),
  logout: () => apiRequest<null>("/api/v1/auth/web/logout", { method: "POST" }),
  completeOnboarding: () =>
    apiRequest<User>("/api/v1/me/onboarding", { method: "POST" }),
  roadmaps: () => apiRequest<RoadmapListItem[]>("/api/v1/roadmaps"),
  roadmap: (slug: string) =>
    apiRequest<RoadmapDetail>(`/api/v1/roadmaps/${slug}`),
  startRoadmap: (slug: string) =>
    apiRequest<RoadmapDetail>(`/api/v1/roadmaps/${slug}/start`, {
      method: "POST",
    }),
  topic: (id: string) => apiRequest<TopicDetail>(`/api/v1/topics/${id}`),
  updateProgress: (id: string, status: ProgressStatus) =>
    apiRequest<ProgressUpdateResponse>(`/api/v1/me/topics/${id}/progress`, {
      method: "PUT",
      body: JSON.stringify({ status }),
    }),
  mentorStudents: () =>
    apiRequest<MentorStudentListItem[]>("/api/v1/mentor/students"),
  mentorStudent: (id: string) =>
    apiRequest<MentorStudentDetail>(`/api/v1/mentor/students/${id}`),
  adminRoadmaps: () => apiRequest<AdminRoadmapRead[]>("/api/v1/admin/roadmaps"),
  adminRoadmapSummaries: () =>
    apiRequest<AdminRoadmapSummary[]>("/api/v1/admin/roadmaps/summaries"),
  adminRoadmapOutline: (id: string) =>
    apiRequest<AdminRoadmapOutline>(`/api/v1/admin/roadmaps/${id}/outline`),
  updateAdminRoadmapSettings: (
    id: string,
    payload: AdminRoadmapSettingsMutation,
  ) =>
    apiRequest<AdminRoadmapOutline>(`/api/v1/admin/roadmaps/${id}/outline`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    }),
  adminRoadmapSection: (roadmapId: string, sectionId: string) =>
    apiRequest<AdminSectionOutline>(
      `/api/v1/admin/roadmaps/${roadmapId}/sections/${sectionId}`,
    ),
  createAdminRoadmapSection: (
    roadmapId: string,
    payload: AdminSectionMutation,
  ) =>
    apiRequest<AdminSectionOutline>(
      `/api/v1/admin/roadmaps/${roadmapId}/sections`,
      { method: "POST", body: JSON.stringify(payload) },
    ),
  updateAdminRoadmapSection: (
    roadmapId: string,
    sectionId: string,
    payload: AdminSectionMutation,
  ) =>
    apiRequest<AdminSectionOutline>(
      `/api/v1/admin/roadmaps/${roadmapId}/sections/${sectionId}`,
      { method: "PUT", body: JSON.stringify(payload) },
    ),
  adminRoadmapTopic: (roadmapId: string, sectionId: string, topicId: string) =>
    apiRequest<AdminTopicRead>(
      `/api/v1/admin/roadmaps/${roadmapId}/sections/${sectionId}/topics/${topicId}`,
    ),
  createAdminRoadmapTopic: (
    roadmapId: string,
    sectionId: string,
    payload: AdminTopicCreate,
  ) =>
    apiRequest<AdminTopicRead>(
      `/api/v1/admin/roadmaps/${roadmapId}/sections/${sectionId}/topics`,
      { method: "POST", body: JSON.stringify(payload) },
    ),
  updateAdminRoadmapTopic: (
    roadmapId: string,
    sectionId: string,
    topicId: string,
    payload: AdminTopicCreate,
  ) =>
    apiRequest<AdminTopicRead>(
      `/api/v1/admin/roadmaps/${roadmapId}/sections/${sectionId}/topics/${topicId}`,
      { method: "PUT", body: JSON.stringify(payload) },
    ),
  adminRoadmap: (id: string) =>
    apiRequest<AdminRoadmapRead>(`/api/v1/admin/roadmaps/${id}`),
  createAdminRoadmap: (payload: AdminRoadmapCreate) =>
    apiRequest<AdminRoadmapRead>("/api/v1/admin/roadmaps", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  updateAdminRoadmap: (id: string, payload: AdminRoadmapUpdate) =>
    apiRequest<AdminRoadmapRead>(`/api/v1/admin/roadmaps/${id}`, {
      method: "PUT",
      body: JSON.stringify(payload),
    }),
  adminTracks: () => apiRequest<AdminTrackRead[]>("/api/v1/admin/tracks"),
  adminTrack: (id: string) =>
    apiRequest<AdminTrackRead>(`/api/v1/admin/tracks/${id}`),
  adminTrackOptions: () =>
    apiRequest<AdminTrackOptions>("/api/v1/admin/tracks/options"),
  createAdminTrack: (payload: AdminTrackMutation) =>
    apiRequest<AdminTrackRead>("/api/v1/admin/tracks", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  updateAdminTrack: (id: string, payload: AdminTrackMutation) =>
    apiRequest<AdminTrackRead>(`/api/v1/admin/tracks/${id}`, {
      method: "PUT",
      body: JSON.stringify(payload),
    }),
  grantAdminTrackAccess: (trackId: string, studentId: string) =>
    apiRequest(`/api/v1/admin/tracks/${trackId}/students/${studentId}`, {
      method: "PUT",
    }),
  revokeAdminTrackAccess: (trackId: string, studentId: string) =>
    apiRequest<void>(`/api/v1/admin/tracks/${trackId}/students/${studentId}`, {
      method: "DELETE",
    }),
  knowledgeTopics: () =>
    apiRequest<KnowledgeTopicListItem[]>("/api/v1/knowledge/topics"),
  knowledgeTopic: (slug: string) =>
    apiRequest<KnowledgeTopicDetail>(`/api/v1/knowledge/topics/${slug}`),
  knowledgeEntry: (slug: string) =>
    apiRequest<KnowledgeEntryDetail>(`/api/v1/knowledge/entries/${slug}`),
  knowledgeSearch: (query: string) =>
    apiRequest<KnowledgeSearchResult[]>(
      `/api/v1/knowledge/search?q=${encodeURIComponent(query)}`,
    ),
  adminKnowledgeTopics: () =>
    apiRequest<AdminKnowledgeTopicRead[]>("/api/v1/admin/knowledge/topics"),
  adminKnowledgeTopicSummaries: () =>
    apiRequest<AdminKnowledgeTopicSummary[]>(
      "/api/v1/admin/knowledge/topics/summaries",
    ),
  adminKnowledgeTopicOutline: (id: string) =>
    apiRequest<AdminKnowledgeTopicOutline>(
      `/api/v1/admin/knowledge/topics/${id}/outline`,
    ),
  updateAdminKnowledgeTopicSettings: (
    id: string,
    payload: AdminKnowledgeTopicSettingsMutation,
  ) =>
    apiRequest<AdminKnowledgeTopicOutline>(
      `/api/v1/admin/knowledge/topics/${id}/outline`,
      { method: "PATCH", body: JSON.stringify(payload) },
    ),
  adminKnowledgeEntry: (topicId: string, entryId: string) =>
    apiRequest<AdminKnowledgeEntryRead>(
      `/api/v1/admin/knowledge/topics/${topicId}/entries/${entryId}`,
    ),
  createAdminKnowledgeEntry: (
    topicId: string,
    payload: AdminKnowledgeEntryMutation,
  ) =>
    apiRequest<AdminKnowledgeEntryRead>(
      `/api/v1/admin/knowledge/topics/${topicId}/entries`,
      { method: "POST", body: JSON.stringify(payload) },
    ),
  updateAdminKnowledgeEntry: (
    topicId: string,
    entryId: string,
    payload: AdminKnowledgeEntryMutation,
  ) =>
    apiRequest<AdminKnowledgeEntryRead>(
      `/api/v1/admin/knowledge/topics/${topicId}/entries/${entryId}`,
      { method: "PUT", body: JSON.stringify(payload) },
    ),
  adminKnowledgeTopic: (id: string) =>
    apiRequest<AdminKnowledgeTopicRead>(`/api/v1/admin/knowledge/topics/${id}`),
  createAdminKnowledgeTopic: (payload: AdminKnowledgeTopicMutation) =>
    apiRequest<AdminKnowledgeTopicRead>("/api/v1/admin/knowledge/topics", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  updateAdminKnowledgeTopic: (
    id: string,
    payload: AdminKnowledgeTopicMutation,
  ) =>
    apiRequest<AdminKnowledgeTopicRead>(
      `/api/v1/admin/knowledge/topics/${id}`,
      {
        method: "PUT",
        body: JSON.stringify(payload),
      },
    ),
  interviewDecks: () =>
    apiRequest<InterviewDeckListItem[]>("/api/v1/interviews/decks"),
  interviewSession: (deckSlug: string) =>
    apiRequest<InterviewStudySession>(
      `/api/v1/interviews/decks/${deckSlug}/session`,
    ),
  interviewTopics: (deckSlug: string) =>
    apiRequest<InterviewTopicOption[]>(
      `/api/v1/interviews/decks/${deckSlug}/topics`,
    ),
  updateInterviewTopics: (deckSlug: string, categories: string[]) =>
    apiRequest<InterviewTopicOption[]>(
      `/api/v1/interviews/decks/${deckSlug}/topics`,
      {
        method: "PUT",
        body: JSON.stringify({ categories }),
      },
    ),
  reviewInterviewCard: (cardId: string, rating: InterviewReviewRating) =>
    apiRequest<InterviewReviewResult>(
      `/api/v1/interviews/cards/${cardId}/reviews`,
      {
        method: "POST",
        body: JSON.stringify({ rating }),
      },
    ),
  adminInterviewDecks: () =>
    apiRequest<AdminInterviewDeckRead[]>("/api/v1/admin/interviews/decks"),
  adminInterviewDeckSummaries: () =>
    apiRequest<AdminInterviewDeckSummary[]>(
      "/api/v1/admin/interviews/decks/summaries",
    ),
  adminInterviewDeckOverview: (id: string) =>
    apiRequest<AdminInterviewDeckSummary>(
      `/api/v1/admin/interviews/decks/${id}/overview`,
    ),
  updateAdminInterviewDeckSettings: (
    id: string,
    payload: AdminInterviewDeckSettingsMutation,
  ) =>
    apiRequest<AdminInterviewDeckSummary>(
      `/api/v1/admin/interviews/decks/${id}/overview`,
      { method: "PATCH", body: JSON.stringify(payload) },
    ),
  adminInterviewCards: (
    deckId: string,
    options: { query?: string; limit?: number; offset?: number } = {},
  ) => {
    const params = new URLSearchParams({
      limit: String(options.limit ?? 50),
      offset: String(options.offset ?? 0),
    });
    if (options.query) params.set("q", options.query);
    return apiRequest<AdminInterviewCardPage>(
      `/api/v1/admin/interviews/decks/${deckId}/cards?${params}`,
    );
  },
  adminInterviewCard: (deckId: string, cardId: string) =>
    apiRequest<AdminInterviewCardRead>(
      `/api/v1/admin/interviews/decks/${deckId}/cards/${cardId}`,
    ),
  createAdminInterviewCard: (
    deckId: string,
    payload: AdminInterviewCardMutation,
  ) =>
    apiRequest<AdminInterviewCardRead>(
      `/api/v1/admin/interviews/decks/${deckId}/cards`,
      { method: "POST", body: JSON.stringify(payload) },
    ),
  updateAdminInterviewCard: (
    deckId: string,
    cardId: string,
    payload: AdminInterviewCardMutation,
  ) =>
    apiRequest<AdminInterviewCardRead>(
      `/api/v1/admin/interviews/decks/${deckId}/cards/${cardId}`,
      { method: "PUT", body: JSON.stringify(payload) },
    ),
  adminInterviewDeck: (id: string) =>
    apiRequest<AdminInterviewDeckRead>(`/api/v1/admin/interviews/decks/${id}`),
  createAdminInterviewDeck: (payload: AdminInterviewDeckMutation) =>
    apiRequest<AdminInterviewDeckRead>("/api/v1/admin/interviews/decks", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  updateAdminInterviewDeck: (id: string, payload: AdminInterviewDeckMutation) =>
    apiRequest<AdminInterviewDeckRead>(`/api/v1/admin/interviews/decks/${id}`, {
      method: "PUT",
      body: JSON.stringify(payload),
    }),
};
