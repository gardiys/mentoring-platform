import type {
  AdminKnowledgeTopicMutation,
  AdminKnowledgeTopicRead,
  AdminInterviewDeckMutation,
  AdminInterviewDeckRead,
  AdminRoadmapCreate,
  AdminRoadmapRead,
  AdminRoadmapUpdate,
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
