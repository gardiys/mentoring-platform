import type {
  AdminQuestionModerationDetail,
  AdminQuestionModerationPage,
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
  AdminScheduleEventMutation,
  AdminScheduleEventPageRead,
  AdminSectionMutation,
  AdminSectionOutline,
  AdminStudentDetail,
  AdminStudentMutation,
  AdminStudentOptions,
  AdminStudentPage,
  AdminMentorCandidate,
  AdminMentorListItem,
  AdminMentorMutation,
  AdminMentorProfileMutation,
  AdminInterviewProcessPage,
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
  InterviewDirectionOption,
  InterviewReviewRating,
  InterviewReviewResult,
  InterviewStudySession,
  InterviewTopicOption,
  InterviewProcessDetail,
  InterviewProcessMutation,
  InterviewProcessOutcomeMutation,
  InterviewProcessRecruitersMutation,
  InterviewProcessStageMutation,
  InterviewProcessStatus,
  InterviewProcessSummary,
  InterviewUploadIntent,
  InterviewDownloadUrl,
  InterviewCatalogCommentMutation,
  InterviewCatalogCommentRead,
  InterviewCatalogAuthorRead,
  InterviewCatalogCompanyDetail,
  InterviewCatalogCompanyPage,
  InterviewCatalogFilters,
  IntelligenceInterviewDetail,
  IntelligenceInterviewPage,
  IntelligenceProcessing,
  IntelligenceReview,
  CompanyOption,
  ContentMediaPlayback,
  ContentMediaUploadIntent,
  ContentMediaUploadMetadata,
  MentorDocumentKind,
  MentorDocumentRead,
  MentorInterviewDetail,
  MentorNoteRead,
  MentorOneOffActivityMutation,
  MentorProfileRead,
  MentorStudentDetail,
  MentorStudentPage,
  MentorWeeklyCallMutation,
  MentorWeeklyCallRescheduleMutation,
  MockInterviewRead,
  MyMentorDashboardRead,
  PinnedResourceLinkMutation,
  PinnedResourceLinkRead,
  ProtectedContentMediaRead,
  ScheduleEventKind,
  ScheduleEventRead,
  StudentLearningStatus,
  StudentStrengthLevel,
  ProgressStatus,
  ProgressUpdateResponse,
  RoadmapDetail,
  RoadmapListItem,
  TopicDetail,
  User,
} from "../types/api";
import {
  apiRequest,
  resolveApiUrl,
  uploadPresignedPost,
  type UploadOptions,
} from "./client";
import { inferFileContentType } from "../utils/media";

async function uploadInterviewFile(
  intentPath: string,
  completePath: string,
  file: File,
  options?: UploadOptions,
): Promise<InterviewProcessDetail> {
  const payload = {
    filename: file.name,
    content_type: inferFileContentType(file),
    size: file.size,
  };
  const intent = await apiRequest<InterviewUploadIntent>(intentPath, {
    method: "POST",
    body: JSON.stringify(payload),
    signal: options?.signal,
  });
  await uploadPresignedPost(intent, file, options);
  return apiRequest<InterviewProcessDetail>(completePath, {
    method: "POST",
    body: JSON.stringify({ ...payload, storage_key: intent.storage_key }),
    signal: options?.signal,
  });
}

async function uploadProtectedContentMedia(
  intentPath: string,
  finalizePath: string,
  file: File,
  metadata: ContentMediaUploadMetadata,
  options?: UploadOptions,
): Promise<ProtectedContentMediaRead> {
  const payload = {
    filename: file.name,
    content_type: inferFileContentType(file),
    size: file.size,
  };
  const intent = await apiRequest<ContentMediaUploadIntent>(intentPath, {
    method: "POST",
    body: JSON.stringify(payload),
    signal: options?.signal,
  });
  await uploadPresignedPost(intent, file, options);
  return apiRequest<ProtectedContentMediaRead>(finalizePath, {
    method: "POST",
    body: JSON.stringify({
      ...payload,
      storage_key: intent.storage_key,
      title: metadata.title,
      position: metadata.position,
    }),
    signal: options?.signal,
  });
}

async function uploadMentorFile<T>(
  intentPath: string,
  completePath: string,
  file: File,
  options?: UploadOptions,
): Promise<T> {
  const payload = {
    filename: file.name,
    content_type: inferFileContentType(file),
    size: file.size,
  };
  const intent = await apiRequest<InterviewUploadIntent>(intentPath, {
    method: "POST",
    body: JSON.stringify(payload),
    signal: options?.signal,
  });
  await uploadPresignedPost(intent, file, options);
  return apiRequest<T>(completePath, {
    method: "POST",
    body: JSON.stringify({ ...payload, storage_key: intent.storage_key }),
    signal: options?.signal,
  });
}

export const api = {
  me: () => apiRequest<User>("/api/v1/me"),
  logout: () => apiRequest<null>("/api/v1/auth/web/logout", { method: "POST" }),
  completeOnboarding: () =>
    apiRequest<User>("/api/v1/me/onboarding", { method: "POST" }),
  intelligenceInterviews: (options: { limit?: number; offset?: number } = {}) =>
    apiRequest<IntelligenceInterviewPage>(
      `/api/v1/interviews?limit=${options.limit ?? 20}&offset=${options.offset ?? 0}`,
    ),
  adminQuestionModeration: (
    options: {
      status?:
        "needs_review" | "mentor_approved" | "approved" | "rejected" | "all";
      q?: string;
      limit?: number;
      offset?: number;
    } = {},
  ) => {
    const params = new URLSearchParams({
      status: options.status ?? "needs_review",
      limit: String(options.limit ?? 20),
      offset: String(options.offset ?? 0),
    });
    if (options.q) params.set("q", options.q);
    return apiRequest<AdminQuestionModerationPage>(
      `/api/v1/admin/interviews/question-moderation?${params.toString()}`,
    );
  },
  adminQuestionModerationDetail: (questionId: string) =>
    apiRequest<AdminQuestionModerationDetail>(
      `/api/v1/admin/interviews/question-moderation/${questionId}`,
    ),
  intelligenceInterview: (id: string) =>
    apiRequest<IntelligenceInterviewDetail>(`/api/v1/interviews/${id}`),
  intelligenceInterviewProcessing: (id: string) =>
    apiRequest<IntelligenceProcessing>(`/api/v1/interviews/${id}/processing`),
  startInterviewStageAnalysis: (processId: string, stageId: string) =>
    apiRequest<IntelligenceInterviewDetail>(
      `/api/v1/interviews/journal/tracks/${processId}/stages/${stageId}/ai-analysis`,
      { method: "POST" },
    ),
  selectIntelligenceCandidate: (id: string, speakerId: string) =>
    apiRequest<IntelligenceInterviewDetail>(
      `/api/v1/interviews/${id}/candidate-speaker`,
      { method: "PUT", body: JSON.stringify({ speaker_id: speakerId }) },
    ),
  retryIntelligenceInterview: (id: string) =>
    apiRequest<IntelligenceInterviewDetail>(`/api/v1/interviews/${id}/retry`, {
      method: "POST",
    }),
  intelligenceMedia: (id: string) =>
    apiRequest<{ url: string; content_type: string }>(
      `/api/v1/interviews/${id}/media`,
    ),
  deleteIntelligenceInterview: (id: string) =>
    apiRequest<void>(`/api/v1/interviews/${id}`, { method: "DELETE" }),
  mentorIntelligenceInterviews: (
    reviewStatus: "needs_review" | "reviewed" | "processing" | "all",
    options: { limit?: number; offset?: number } = {},
  ) =>
    apiRequest<IntelligenceInterviewPage>(
      `/api/v1/mentor/interviews?status=${reviewStatus}&limit=${options.limit ?? 20}&offset=${options.offset ?? 0}`,
    ),
  addIntelligenceMentorComment: (
    id: string,
    payload: {
      question_id?: string | null;
      timestamp_ms?: number | null;
      text: string;
    },
  ) =>
    apiRequest(`/api/v1/mentor/interviews/${id}/comments`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  approveIntelligenceReview: (interviewId: string, reviewId: string) =>
    apiRequest<IntelligenceReview>(
      `/api/v1/mentor/interviews/${interviewId}/reviews/${reviewId}/approve`,
      { method: "POST" },
    ),
  rejectIntelligenceReview: (interviewId: string, reviewId: string) =>
    apiRequest<IntelligenceReview>(
      `/api/v1/mentor/interviews/${interviewId}/reviews/${reviewId}/reject`,
      { method: "POST", body: JSON.stringify({ reason: "other" }) },
    ),
  moderateIntelligenceQuestion: (
    interviewId: string,
    questionId: string,
    payload: {
      action: "recommend" | "approve" | "reject";
      question_markdown?: string;
      answer_markdown?: string;
      category?: string;
      frequency?: "frequent" | "occasional";
    },
  ) =>
    apiRequest<IntelligenceInterviewDetail>(
      `/api/v1/mentor/interviews/${interviewId}/questions/${questionId}/moderation`,
      { method: "POST", body: JSON.stringify(payload) },
    ),
  completeIntelligenceReview: (interviewId: string) =>
    apiRequest<IntelligenceInterviewDetail>(
      `/api/v1/mentor/interviews/${interviewId}/complete-review`,
      { method: "POST" },
    ),
  generateIntelligenceOverview: (interviewId: string) =>
    apiRequest<IntelligenceInterviewDetail>(
      `/api/v1/mentor/interviews/${interviewId}/generate-overview`,
      { method: "POST" },
    ),
  roadmaps: () => apiRequest<RoadmapListItem[]>("/api/v1/roadmaps"),
  roadmap: (slug: string) =>
    apiRequest<RoadmapDetail>(`/api/v1/roadmaps/${slug}`),
  startRoadmap: (slug: string, startedOn: string) =>
    apiRequest<RoadmapDetail>(`/api/v1/roadmaps/${slug}/start`, {
      method: "POST",
      body: JSON.stringify({ started_on: startedOn }),
    }),
  topic: (id: string) => apiRequest<TopicDetail>(`/api/v1/topics/${id}`),
  roadmapTopicMediaPlayback: (topicId: string, mediaId: string) =>
    apiRequest<ContentMediaPlayback>(
      `/api/v1/topics/${topicId}/media/${mediaId}/playback`,
    ).then((result) => ({ ...result, url: resolveApiUrl(result.url) })),
  updateProgress: (id: string, status: ProgressStatus) =>
    apiRequest<ProgressUpdateResponse>(`/api/v1/me/topics/${id}/progress`, {
      method: "PUT",
      body: JSON.stringify({ status }),
    }),
  myMentorDashboard: () =>
    apiRequest<MyMentorDashboardRead>("/api/v1/me/mentor"),
  mentorProfile: () => apiRequest<MentorProfileRead>("/api/v1/mentor/profile"),
  updateMentorProfile: (payload: {
    consultation_url: string | null;
    group_calendar_url: string | null;
  }) =>
    apiRequest<MentorProfileRead>("/api/v1/mentor/profile", {
      method: "PUT",
      body: JSON.stringify(payload),
    }),
  createMentorWeeklyCall: (payload: MentorWeeklyCallMutation) =>
    apiRequest<ScheduleEventRead>("/api/v1/mentor/profile/weekly-calls", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  updateMentorWeeklyCall: (
    eventId: string,
    payload: MentorWeeklyCallMutation,
  ) =>
    apiRequest<ScheduleEventRead>(
      `/api/v1/mentor/profile/weekly-calls/${eventId}`,
      { method: "PUT", body: JSON.stringify(payload) },
    ),
  deleteMentorWeeklyCall: (eventId: string) =>
    apiRequest<void>(`/api/v1/mentor/profile/weekly-calls/${eventId}`, {
      method: "DELETE",
    }),
  rescheduleMentorWeeklyCall: (
    eventId: string,
    payload: MentorWeeklyCallRescheduleMutation,
  ) =>
    apiRequest<ScheduleEventRead>(
      `/api/v1/mentor/profile/weekly-calls/${eventId}/reschedule`,
      { method: "PUT", body: JSON.stringify(payload) },
    ),
  cancelMentorWeeklyCallReschedule: (eventId: string) =>
    apiRequest<void>(
      `/api/v1/mentor/profile/weekly-calls/${eventId}/reschedule`,
      { method: "DELETE" },
    ),
  createMentorOneOffActivity: (payload: MentorOneOffActivityMutation) =>
    apiRequest<ScheduleEventRead>("/api/v1/mentor/profile/activities", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  updateMentorOneOffActivity: (
    eventId: string,
    payload: MentorOneOffActivityMutation,
  ) =>
    apiRequest<ScheduleEventRead>(
      `/api/v1/mentor/profile/activities/${eventId}`,
      { method: "PUT", body: JSON.stringify(payload) },
    ),
  deleteMentorOneOffActivity: (eventId: string) =>
    apiRequest<void>(`/api/v1/mentor/profile/activities/${eventId}`, {
      method: "DELETE",
    }),
  mentorStudents: (
    options: {
      query?: string;
      trackId?: string | null;
      mentorId?: string | null;
      withoutMentor?: boolean;
      isActive?: boolean | null;
      learningStatuses?: StudentLearningStatus[];
      limit?: number;
      offset?: number;
    } = {},
  ) => {
    const params = new URLSearchParams({
      limit: String(options.limit ?? 12),
      offset: String(options.offset ?? 0),
    });
    if (options.query) params.set("query", options.query);
    if (options.trackId) params.set("track_id", options.trackId);
    if (options.mentorId) params.set("mentor_id", options.mentorId);
    if (options.withoutMentor) params.set("without_mentor", "true");
    if (options.isActive !== undefined && options.isActive !== null) {
      params.set("is_active", String(options.isActive));
    }
    options.learningStatuses?.forEach((status) =>
      params.append("learning_status", status),
    );
    return apiRequest<MentorStudentPage>(`/api/v1/mentor/students?${params}`);
  },
  mentorStudent: (id: string) =>
    apiRequest<MentorStudentDetail>(`/api/v1/mentor/students/${id}`),
  updateMentorStudentState: (
    id: string,
    learningStatus: StudentLearningStatus,
    strengthLevel: StudentStrengthLevel | null,
  ) =>
    apiRequest<MentorStudentDetail>(`/api/v1/mentor/students/${id}/state`, {
      method: "PATCH",
      body: JSON.stringify({
        learning_status: learningStatus,
        strength_level: strengthLevel,
      }),
    }),
  createMentorNote: (studentId: string, body: string) =>
    apiRequest<MentorNoteRead>(`/api/v1/mentor/students/${studentId}/notes`, {
      method: "POST",
      body: JSON.stringify({ body }),
    }),
  updateMentorNote: (studentId: string, noteId: string, body: string) =>
    apiRequest<MentorNoteRead>(
      `/api/v1/mentor/students/${studentId}/notes/${noteId}`,
      { method: "PUT", body: JSON.stringify({ body }) },
    ),
  deleteMentorNote: (studentId: string, noteId: string) =>
    apiRequest<void>(`/api/v1/mentor/students/${studentId}/notes/${noteId}`, {
      method: "DELETE",
    }),
  setMentorDocumentText: (
    studentId: string,
    kind: MentorDocumentKind,
    textContent: string | null,
    keepFile = true,
  ) =>
    apiRequest<MentorDocumentRead>(
      `/api/v1/mentor/students/${studentId}/documents/${kind}`,
      {
        method: "PUT",
        body: JSON.stringify({
          text_content: textContent,
          keep_file: keepFile,
        }),
      },
    ),
  uploadMentorDocument: (
    studentId: string,
    kind: MentorDocumentKind,
    file: File,
  ) =>
    uploadMentorFile<MentorDocumentRead>(
      `/api/v1/mentor/students/${studentId}/documents/${kind}/upload`,
      `/api/v1/mentor/students/${studentId}/documents/${kind}/complete`,
      file,
    ),
  openMentorDocument: (studentId: string, kind: MentorDocumentKind) =>
    apiRequest<InterviewDownloadUrl>(
      `/api/v1/mentor/students/${studentId}/documents/${kind}/file`,
    ).then((result) => result.url),
  createMockInterview: (
    studentId: string,
    payload: { scheduled_at: string; description: string | null },
  ) =>
    apiRequest<MockInterviewRead>(
      `/api/v1/mentor/students/${studentId}/mock-interviews`,
      { method: "POST", body: JSON.stringify(payload) },
    ),
  completeMockInterview: (
    studentId: string,
    mockId: string,
    feedback: string,
  ) =>
    apiRequest<MockInterviewRead>(
      `/api/v1/mentor/students/${studentId}/mock-interviews/${mockId}/feedback`,
      { method: "PATCH", body: JSON.stringify({ feedback }) },
    ),
  uploadMockInterviewMedia: (
    studentId: string,
    mockId: string,
    file: File,
    options?: UploadOptions,
  ) =>
    uploadMentorFile<MockInterviewRead>(
      `/api/v1/mentor/students/${studentId}/mock-interviews/${mockId}/media/upload`,
      `/api/v1/mentor/students/${studentId}/mock-interviews/${mockId}/media/complete`,
      file,
      options,
    ),
  openMockInterviewMedia: (studentId: string, mockId: string) =>
    apiRequest<InterviewDownloadUrl>(
      `/api/v1/mentor/students/${studentId}/mock-interviews/${mockId}/media`,
    ).then((result) => result.url),
  mentorInterview: (studentId: string, processId: string) =>
    apiRequest<MentorInterviewDetail>(
      `/api/v1/mentor/students/${studentId}/interviews/${processId}`,
    ),
  createMentorInterviewFeedback: (
    studentId: string,
    stageId: string,
    body: string,
  ) =>
    apiRequest<InterviewCatalogCommentRead>(
      `/api/v1/mentor/students/${studentId}/interviews/stages/${stageId}/feedback`,
      { method: "POST", body: JSON.stringify({ body }) },
    ),
  openMentorInterviewAttachment: (
    studentId: string,
    processId: string,
    stageId: string,
    attachmentId: string,
  ) =>
    apiRequest<InterviewDownloadUrl>(
      `/api/v1/mentor/students/${studentId}/interviews/${processId}/stages/${stageId}/attachments/${attachmentId}`,
    ).then((result) => result.url),
  openMentorInterviewOffer: (studentId: string, processId: string) =>
    apiRequest<InterviewDownloadUrl>(
      `/api/v1/mentor/students/${studentId}/interviews/${processId}/offer`,
    ).then((result) => result.url),
  myMockInterviews: () =>
    apiRequest<MockInterviewRead[]>("/api/v1/mentor/me/mock-interviews"),
  openMyMockInterviewMedia: (mockId: string) =>
    apiRequest<InterviewDownloadUrl>(
      `/api/v1/mentor/me/mock-interviews/${mockId}/media`,
    ).then((result) => result.url),
  myMentorDocuments: () =>
    apiRequest<MentorDocumentRead[]>("/api/v1/mentor/me/documents"),
  openMyMentorDocument: (documentId: string) =>
    apiRequest<InterviewDownloadUrl>(
      `/api/v1/mentor/me/documents/${documentId}/file`,
    ).then((result) => result.url),
  adminStudents: (
    options: {
      query?: string;
      trackId?: string | null;
      mentorId?: string | null;
      withoutMentor?: boolean;
      isActive?: boolean | null;
      learningStatuses?: StudentLearningStatus[];
      limit?: number;
      offset?: number;
    } = {},
  ) => {
    const params = new URLSearchParams({
      limit: String(options.limit ?? 50),
      offset: String(options.offset ?? 0),
    });
    if (options.query) params.set("q", options.query);
    if (options.trackId) params.set("track_id", options.trackId);
    if (options.mentorId) params.set("mentor_id", options.mentorId);
    if (options.withoutMentor) params.set("without_mentor", "true");
    if (options.isActive !== undefined && options.isActive !== null) {
      params.set("is_active", String(options.isActive));
    }
    options.learningStatuses?.forEach((status) =>
      params.append("learning_status", status),
    );
    return apiRequest<AdminStudentPage>(`/api/v1/admin/students?${params}`);
  },
  adminStudent: (id: string) =>
    apiRequest<AdminStudentDetail>(`/api/v1/admin/students/${id}`),
  adminStudentOptions: () =>
    apiRequest<AdminStudentOptions>("/api/v1/admin/students/options"),
  createAdminStudent: (payload: AdminStudentMutation) =>
    apiRequest<AdminStudentDetail>("/api/v1/admin/students", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  updateAdminStudent: (id: string, payload: AdminStudentMutation) =>
    apiRequest<AdminStudentDetail>(`/api/v1/admin/students/${id}`, {
      method: "PUT",
      body: JSON.stringify(payload),
    }),
  setAdminStudentAccess: (id: string, isActive: boolean) =>
    apiRequest<AdminStudentDetail>(`/api/v1/admin/students/${id}/access`, {
      method: "PATCH",
      body: JSON.stringify({ is_active: isActive }),
    }),
  adminMentors: () =>
    apiRequest<AdminMentorListItem[]>("/api/v1/admin/mentors"),
  adminMentorCandidates: (query = "") =>
    apiRequest<AdminMentorCandidate[]>(
      `/api/v1/admin/mentors/candidates${query ? `?q=${encodeURIComponent(query)}` : ""}`,
    ),
  createAdminMentor: (payload: AdminMentorMutation) =>
    apiRequest<AdminMentorListItem>("/api/v1/admin/mentors", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  updateAdminMentorProfile: (
    mentorId: string,
    payload: AdminMentorProfileMutation,
  ) =>
    apiRequest<AdminMentorListItem>(
      `/api/v1/admin/mentors/${mentorId}/profile`,
      { method: "PATCH", body: JSON.stringify(payload) },
    ),
  promoteAdminStudent: (studentId: string) =>
    apiRequest<AdminMentorListItem>(
      `/api/v1/admin/mentors/${studentId}/promote`,
      { method: "POST" },
    ),
  removeAdminMentor: (mentorId: string) =>
    apiRequest<void>(`/api/v1/admin/mentors/${mentorId}`, {
      method: "DELETE",
    }),
  updateAdminMentorDirections: (mentorId: string, trackIds: string[]) =>
    apiRequest<AdminMentorListItem>(
      `/api/v1/admin/mentors/${mentorId}/directions`,
      {
        method: "PATCH",
        body: JSON.stringify({ track_ids: trackIds }),
      },
    ),
  reassignAdminMentorStudent: (studentId: string, mentorId: string) =>
    apiRequest<void>(`/api/v1/admin/mentors/students/${studentId}/mentor`, {
      method: "PATCH",
      body: JSON.stringify({ mentor_id: mentorId }),
    }),
  adminScheduleEvents: (
    options: {
      trackId?: string | null;
      kind?: ScheduleEventKind | null;
      limit?: number;
      offset?: number;
    } = {},
  ) => {
    const params = new URLSearchParams({
      limit: String(options.limit ?? 20),
      offset: String(options.offset ?? 0),
    });
    if (options.trackId) params.set("track_id", options.trackId);
    if (options.kind) params.set("kind", options.kind);
    return apiRequest<AdminScheduleEventPageRead>(
      `/api/v1/admin/schedule/events?${params.toString()}`,
    );
  },
  adminScheduleEvent: (eventId: string) =>
    apiRequest<ScheduleEventRead>(`/api/v1/admin/schedule/events/${eventId}`),
  createAdminScheduleEvent: (payload: AdminScheduleEventMutation) =>
    apiRequest<ScheduleEventRead>("/api/v1/admin/schedule/events", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  updateAdminScheduleEvent: (
    eventId: string,
    payload: AdminScheduleEventMutation,
  ) =>
    apiRequest<ScheduleEventRead>(`/api/v1/admin/schedule/events/${eventId}`, {
      method: "PUT",
      body: JSON.stringify(payload),
    }),
  deleteAdminScheduleEvent: (eventId: string) =>
    apiRequest<void>(`/api/v1/admin/schedule/events/${eventId}`, {
      method: "DELETE",
    }),
  adminUsefulLinks: () =>
    apiRequest<PinnedResourceLinkRead[]>("/api/v1/admin/useful-links"),
  createAdminUsefulLink: (payload: PinnedResourceLinkMutation) =>
    apiRequest<PinnedResourceLinkRead>("/api/v1/admin/useful-links", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  updateAdminUsefulLink: (
    linkId: string,
    payload: PinnedResourceLinkMutation,
  ) =>
    apiRequest<PinnedResourceLinkRead>(`/api/v1/admin/useful-links/${linkId}`, {
      method: "PUT",
      body: JSON.stringify(payload),
    }),
  deleteAdminUsefulLink: (linkId: string) =>
    apiRequest<void>(`/api/v1/admin/useful-links/${linkId}`, {
      method: "DELETE",
    }),
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
  uploadAdminRoadmapTopicMedia: (
    roadmapId: string,
    sectionId: string,
    topicId: string,
    file: File,
    metadata: ContentMediaUploadMetadata,
    options?: UploadOptions,
  ) =>
    uploadProtectedContentMedia(
      `/api/v1/admin/roadmaps/${roadmapId}/sections/${sectionId}/topics/${topicId}/media/upload-url`,
      `/api/v1/admin/roadmaps/${roadmapId}/sections/${sectionId}/topics/${topicId}/media/finalize`,
      file,
      metadata,
      options,
    ),
  deleteAdminRoadmapTopicMedia: (
    roadmapId: string,
    sectionId: string,
    topicId: string,
    mediaId: string,
  ) =>
    apiRequest<void>(
      `/api/v1/admin/roadmaps/${roadmapId}/sections/${sectionId}/topics/${topicId}/media/${mediaId}`,
      { method: "DELETE" },
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
  knowledgeMediaPlayback: (entrySlug: string, mediaId: string) =>
    apiRequest<ContentMediaPlayback>(
      `/api/v1/knowledge/entries/${encodeURIComponent(entrySlug)}/media/${mediaId}/playback`,
    ).then((result) => ({ ...result, url: resolveApiUrl(result.url) })),
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
  uploadAdminKnowledgeMedia: (
    topicId: string,
    entryId: string,
    file: File,
    metadata: ContentMediaUploadMetadata,
    options?: UploadOptions,
  ) =>
    uploadProtectedContentMedia(
      `/api/v1/admin/knowledge/topics/${topicId}/entries/${entryId}/media/upload-url`,
      `/api/v1/admin/knowledge/topics/${topicId}/entries/${entryId}/media/finalize`,
      file,
      metadata,
      options,
    ),
  deleteAdminKnowledgeMedia: (
    topicId: string,
    entryId: string,
    mediaId: string,
  ) =>
    apiRequest<void>(
      `/api/v1/admin/knowledge/topics/${topicId}/entries/${entryId}/media/${mediaId}`,
      { method: "DELETE" },
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
  interviewProcesses: (status: InterviewProcessStatus | "all" = "all") =>
    apiRequest<InterviewProcessSummary[]>(
      `/api/v1/interviews/journal/tracks?status=${status}`,
    ),
  interviewCompanySuggestions: (query: string) =>
    apiRequest<CompanyOption[]>(
      `/api/v1/interviews/journal/companies?q=${encodeURIComponent(query)}`,
    ),
  interviewDirections: () =>
    apiRequest<InterviewDirectionOption[]>(
      "/api/v1/interviews/journal/directions",
    ),
  interviewProcess: (id: string) =>
    apiRequest<InterviewProcessDetail>(
      `/api/v1/interviews/journal/tracks/${id}`,
    ),
  createInterviewProcess: (payload: InterviewProcessMutation) =>
    apiRequest<InterviewProcessDetail>("/api/v1/interviews/journal/tracks", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  updateInterviewProcess: (id: string, payload: InterviewProcessMutation) =>
    apiRequest<InterviewProcessDetail>(
      `/api/v1/interviews/journal/tracks/${id}`,
      { method: "PUT", body: JSON.stringify(payload) },
    ),
  setInterviewProcessRecruiters: (
    id: string,
    payload: InterviewProcessRecruitersMutation,
  ) =>
    apiRequest<InterviewProcessDetail>(
      `/api/v1/interviews/journal/tracks/${id}/recruiters`,
      { method: "PATCH", body: JSON.stringify(payload) },
    ),
  setInterviewProcessOutcome: (
    id: string,
    payload: InterviewProcessOutcomeMutation,
  ) =>
    apiRequest<InterviewProcessDetail>(
      `/api/v1/interviews/journal/tracks/${id}/outcome`,
      { method: "PATCH", body: JSON.stringify(payload) },
    ),
  createInterviewProcessStage: (
    processId: string,
    payload: InterviewProcessStageMutation,
  ) =>
    apiRequest<InterviewProcessDetail>(
      `/api/v1/interviews/journal/tracks/${processId}/stages`,
      { method: "POST", body: JSON.stringify(payload) },
    ),
  updateInterviewProcessStage: (
    processId: string,
    stageId: string,
    payload: InterviewProcessStageMutation,
  ) =>
    apiRequest<InterviewProcessDetail>(
      `/api/v1/interviews/journal/tracks/${processId}/stages/${stageId}`,
      { method: "PUT", body: JSON.stringify(payload) },
    ),
  uploadInterviewStageMedia: (
    processId: string,
    stageId: string,
    file: File,
    options?: UploadOptions,
  ) =>
    uploadInterviewFile(
      `/api/v1/interviews/journal/tracks/${processId}/stages/${stageId}/media/upload`,
      `/api/v1/interviews/journal/tracks/${processId}/stages/${stageId}/media/complete`,
      file,
      options,
    ),
  downloadInterviewStageMedia: (processId: string, stageId: string) =>
    apiRequest<InterviewDownloadUrl>(
      `/api/v1/interviews/journal/tracks/${processId}/stages/${stageId}/media`,
    ).then((result) => result.url),
  viewInterviewStageMedia: (processId: string, stageId: string) =>
    apiRequest<InterviewDownloadUrl>(
      `/api/v1/interviews/journal/tracks/${processId}/stages/${stageId}/media?inline=true`,
    ).then((result) => result.url),
  deleteInterviewStageMedia: (processId: string, stageId: string) =>
    apiRequest<void>(
      `/api/v1/interviews/journal/tracks/${processId}/stages/${stageId}/media`,
      { method: "DELETE" },
    ),
  uploadInterviewStageAttachment: (
    processId: string,
    stageId: string,
    file: File,
  ) =>
    uploadInterviewFile(
      `/api/v1/interviews/journal/tracks/${processId}/stages/${stageId}/attachments/upload`,
      `/api/v1/interviews/journal/tracks/${processId}/stages/${stageId}/attachments/complete`,
      file,
    ),
  downloadInterviewStageAttachment: (
    processId: string,
    stageId: string,
    attachmentId: string,
  ) =>
    apiRequest<InterviewDownloadUrl>(
      `/api/v1/interviews/journal/tracks/${processId}/stages/${stageId}/attachments/${attachmentId}`,
    ).then((result) => result.url),
  viewInterviewStageAttachment: (
    processId: string,
    stageId: string,
    attachmentId: string,
  ) =>
    apiRequest<InterviewDownloadUrl>(
      `/api/v1/interviews/journal/tracks/${processId}/stages/${stageId}/attachments/${attachmentId}?inline=true`,
    ).then((result) => result.url),
  deleteInterviewStageAttachment: (
    processId: string,
    stageId: string,
    attachmentId: string,
  ) =>
    apiRequest<void>(
      `/api/v1/interviews/journal/tracks/${processId}/stages/${stageId}/attachments/${attachmentId}`,
      { method: "DELETE" },
    ),
  uploadInterviewOffer: (processId: string, file: File) =>
    uploadInterviewFile(
      `/api/v1/interviews/journal/tracks/${processId}/offer/upload`,
      `/api/v1/interviews/journal/tracks/${processId}/offer/complete`,
      file,
    ),
  downloadInterviewOffer: (processId: string) =>
    apiRequest<InterviewDownloadUrl>(
      `/api/v1/interviews/journal/tracks/${processId}/offer`,
    ).then((result) => result.url),
  deleteInterviewOffer: (processId: string) =>
    apiRequest<void>(`/api/v1/interviews/journal/tracks/${processId}/offer`, {
      method: "DELETE",
    }),
  interviewCatalogCompanies: (
    filters: InterviewCatalogFilters,
    options: { limit?: number; offset?: number } = {},
  ) => {
    const params = new URLSearchParams({
      limit: String(options.limit ?? 24),
      offset: String(options.offset ?? 0),
    });
    if (filters.query) params.set("q", filters.query);
    if (filters.authorId) params.set("author_id", filters.authorId);
    if (filters.trackId) params.set("track_id", filters.trackId);
    if (filters.stageType) params.set("stage_type", filters.stageType);
    if (filters.hasOffer) params.set("has_offer", "true");
    if (filters.mediaKind) params.set("media_kind", filters.mediaKind);
    const query = params.toString();
    return apiRequest<InterviewCatalogCompanyPage>(
      `/api/v1/interviews/catalog/companies${query ? `?${query}` : ""}`,
    );
  },
  interviewCatalogCompany: (
    companyId: string,
    filters: InterviewCatalogFilters,
  ) => {
    const params = new URLSearchParams();
    if (filters.authorId) params.set("author_id", filters.authorId);
    if (filters.trackId) params.set("track_id", filters.trackId);
    if (filters.stageType) params.set("stage_type", filters.stageType);
    if (filters.hasOffer) params.set("has_offer", "true");
    if (filters.mediaKind) params.set("media_kind", filters.mediaKind);
    const query = params.toString();
    return apiRequest<InterviewCatalogCompanyDetail>(
      `/api/v1/interviews/catalog/companies/${companyId}${query ? `?${query}` : ""}`,
    );
  },
  interviewCatalogDirections: () =>
    apiRequest<InterviewDirectionOption[]>(
      "/api/v1/interviews/catalog/directions",
    ),
  interviewCatalogAuthors: () =>
    apiRequest<InterviewCatalogAuthorRead[]>(
      "/api/v1/interviews/catalog/authors",
    ),
  interviewCatalogStageMedia: (stageId: string) =>
    apiRequest<InterviewDownloadUrl>(
      `/api/v1/interviews/catalog/stages/${stageId}/media`,
    ).then((result) => resolveApiUrl(result.url)),
  interviewCatalogStageAttachment: (
    stageId: string,
    attachmentId: string,
    inline = false,
  ) =>
    apiRequest<InterviewDownloadUrl>(
      `/api/v1/interviews/catalog/stages/${stageId}/attachments/${attachmentId}?inline=${inline}`,
    ).then((result) => result.url),
  createInterviewCatalogComment: (
    stageId: string,
    payload: InterviewCatalogCommentMutation,
  ) =>
    apiRequest<InterviewCatalogCommentRead>(
      `/api/v1/interviews/catalog/stages/${stageId}/comments`,
      { method: "POST", body: JSON.stringify(payload) },
    ),
  deleteInterviewCatalogComment: (commentId: string) =>
    apiRequest<void>(`/api/v1/interviews/catalog/comments/${commentId}`, {
      method: "DELETE",
    }),
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
  adminInterviewProcesses: (
    status: InterviewProcessStatus | "all" = "all",
    options: { limit?: number; offset?: number } = {},
  ) => {
    const params = new URLSearchParams({
      status,
      limit: String(options.limit ?? 24),
      offset: String(options.offset ?? 0),
    });
    return apiRequest<AdminInterviewProcessPage>(
      `/api/v1/admin/interviews/processes?${params}`,
    );
  },
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
