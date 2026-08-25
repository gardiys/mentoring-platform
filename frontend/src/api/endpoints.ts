import type {
  AdminQuestionModerationDetail,
  AdminQuestionModerationPage,
  AutomationDecisionFilters,
  AutomationDecisionOverrideMutation,
  AutomationDecisionPage,
  AutomationDecisionRead,
  AutomationDecisionReviewMutation,
  CardAutomationSettingsMutation,
  CardAutomationSettingsPage,
  CardAutomationSettingsRead,
  CardAutomationMetricsFilters,
  CardAutomationMetricsRead,
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
  AdminCompanyAliasProposalMutation,
  AdminCompanyAliasProposalPage,
  AdminCompanyAliasProposalRead,
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
  AdminIntelligenceOperations,
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
  InterviewCardDuplicateMergeMutation,
  InterviewCardDuplicateMutation,
  InterviewCardDuplicatePage,
  InterviewCardDuplicateRefreshRead,
  InterviewCardDuplicateReviewResult,
  InterviewStudySession,
  InterviewTopicOption,
  InterviewProcessDetail,
  InterviewProcessMutation,
  InterviewProcessOutcomeMutation,
  InterviewProcessRecruitersMutation,
  InterviewProcessStageMutation,
  InterviewProcessStatus,
  InterviewProcessSummary,
  RecruiterContactPage,
  RecruiterContactOpenRead,
  RecruiterFeedbackMutation,
  RecruiterFeedbackRead,
  RecruiterSort,
  AdminPaymentPage,
  AdminPaymentStudentPage,
  AdminEmploymentPaymentStatus,
  AdminTochkaTestPaymentRead,
  AdminMentorPayoutDetail,
  AdminMentorPayoutDashboard,
  EmploymentMutation,
  MentorRewardSummary,
  PaymentInstallmentStatus,
  PaymentLinkRead,
  StudentPaymentDashboard,
  InterviewDownloadUrl,
  InterviewCatalogCommentMutation,
  InterviewCatalogCommentRead,
  InterviewCatalogAuthorRead,
  InterviewCatalogCompanyDetail,
  InterviewCatalogCompanyPage,
  InterviewCatalogFilters,
  InterviewCatalogHistoryPage,
  IntelligenceInterviewDetail,
  IntelligenceInterviewPage,
  IntelligenceProcessing,
  IntelligenceReview,
  CompanyOption,
  ContentMediaPlayback,
  ContentMediaUploadMetadata,
  MentorDocumentKind,
  MentorDocumentRead,
  MentorAnalyticsPeriod,
  MentorInterviewAnalytics,
  MentorEfficiencyAnalytics,
  MentorInterviewDetail,
  MentorNoteRead,
  MentorOneOffActivityMutation,
  MentorProfileRead,
  MentorStudentDetail,
  MentorStudentPage,
  MentorStudentSort,
  MentorWeeklyCallMutation,
  MentorWeeklyCallRescheduleMutation,
  ManagedPersonalReviewMutation,
  ManagedPersonalReviewResult,
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
  NotificationPage,
  OnboardingApplicationAction,
  OnboardingApplicationActionResponse,
  OnboardingApplicationDetail,
  OnboardingApplicationPage,
  PersonalReviewFilters,
  PersonalReviewItemPage,
  PersonalReviewMutation,
  PersonalReviewResult,
  QuestionClusterCreateCardMutation,
  QuestionClusterDraftMutation,
  QuestionClusterDetail,
  QuestionClusterFilters,
  QuestionClusterLinkCardMutation,
  QuestionClusterMergeMutation,
  QuestionOccurrenceReprocessMutation,
  QuestionOccurrenceReprocessResult,
  QuestionClusterPage,
  QuestionClusterSplitMutation,
  QuestionClusterActionResult,
  QuestionClusterAnswerGenerationMutation,
  QuestionClusterAnswerGenerationResult,
  QuestionClusterBulkMutation,
  QuestionClusterBulkResult,
  QuestionClusterVersionMutation,
} from "../types/api";
import {
  ApiError,
  abortMultipartUpload,
  apiRequest,
  isMultipartUploadIntent,
  resolveApiUrl,
  uploadStatus,
  uploadStorageIntent,
  type StorageUploadIntent,
  type UploadOptions,
} from "./client";
import { inferFileContentType } from "../utils/media";

const FINALIZE_RETRIES = 3;

async function uploadFile<T>(
  intentPath: string,
  completePath: string,
  file: File,
  completeMetadata: Record<string, unknown>,
  options?: UploadOptions,
): Promise<T> {
  const payload = {
    filename: file.name,
    content_type: inferFileContentType(file),
    size: file.size,
  };
  let intent: StorageUploadIntent | null = null;
  try {
    uploadStatus("preparing", file, options);
    intent = await apiRequest<StorageUploadIntent>(intentPath, {
      method: "POST",
      body: JSON.stringify({ ...payload, upload_protocol: "multipart-v1" }),
      signal: options?.signal,
    });
    const multipartCompletion = await uploadStorageIntent(
      intent,
      file,
      options,
    );
    uploadStatus("finalizing", file, options);
    const completeBody = JSON.stringify({
      ...payload,
      ...completeMetadata,
      storage_key: intent.storage_key,
      ...(multipartCompletion ?? {}),
    });
    return await finalizeUpload<T>(completePath, completeBody, options?.signal);
  } catch (error) {
    if (intent && isMultipartUploadIntent(intent)) {
      void abortMultipartUpload(intent).catch(() => undefined);
    }
    throw error;
  }
}

async function finalizeUpload<T>(
  path: string,
  body: string,
  signal?: AbortSignal,
): Promise<T> {
  for (let retry = 0; retry <= FINALIZE_RETRIES; retry += 1) {
    try {
      return await apiRequest<T>(path, { method: "POST", body, signal });
    } catch (error) {
      if (
        retry >= FINALIZE_RETRIES ||
        !isRetryableFinalizeError(error) ||
        signal?.aborted
      ) {
        throw error;
      }
      await finalizeRetryDelay(500 * 2 ** retry, signal);
    }
  }
  throw new ApiError(0, "upload_finalize_failed", "Не удалось сохранить файл");
}

function isRetryableFinalizeError(error: unknown) {
  return (
    error instanceof ApiError &&
    error.code !== "request_aborted" &&
    (error.status === 0 ||
      error.status === 408 ||
      error.status === 425 ||
      error.status === 429 ||
      error.status >= 500)
  );
}

function finalizeRetryDelay(milliseconds: number, signal?: AbortSignal) {
  return new Promise<void>((resolve, reject) => {
    const timeout = window.setTimeout(() => {
      signal?.removeEventListener("abort", abort);
      resolve();
    }, milliseconds);
    const abort = () => {
      window.clearTimeout(timeout);
      signal?.removeEventListener("abort", abort);
      reject(new ApiError(0, "request_aborted", "Загрузка отменена"));
    };
    if (signal?.aborted) {
      abort();
      return;
    }
    signal?.addEventListener("abort", abort, { once: true });
  });
}

function questionClusterSearchParams(
  filters: QuestionClusterFilters,
  options: { limit?: number; offset?: number },
) {
  const params = new URLSearchParams({
    limit: String(options.limit ?? 20),
    offset: String(options.offset ?? 0),
    needs_action_only: String(filters.needsActionOnly),
    sort_by: filters.sortBy,
    sort_order: filters.sortOrder,
  });
  if (filters.directionId) params.set("direction_id", filters.directionId);
  filters.statuses.forEach((status) => params.append("statuses", status));
  if (filters.topicName) params.set("topic_name", filters.topicName);
  filters.learningObjectTypes.forEach((objectType) =>
    params.append("learning_object_types", objectType),
  );
  if (filters.minDistinctInterviews !== null)
    params.set(
      "min_distinct_interviews",
      String(filters.minDistinctInterviews),
    );
  if (filters.minDistinctCompanies !== null)
    params.set("min_distinct_companies", String(filters.minDistinctCompanies));
  if (filters.hasFailedAnswers !== null)
    params.set("has_failed_answers", String(filters.hasFailedAnswers));
  if (filters.minConfidence !== null)
    params.set("min_confidence", String(filters.minConfidence));
  if (filters.maxConfidence !== null)
    params.set("max_confidence", String(filters.maxConfidence));
  if (filters.hasPossibleDuplicate !== null)
    params.set("has_possible_duplicate", String(filters.hasPossibleDuplicate));
  if (filters.decisionSource)
    params.set("decision_source", filters.decisionSource);
  if (filters.seenFrom) params.set("seen_from", filters.seenFrom);
  if (filters.seenTo) params.set("seen_to", filters.seenTo);
  return params;
}

function automationDecisionSearchParams(
  filters: AutomationDecisionFilters,
  options: { limit?: number; offset?: number },
) {
  const params = new URLSearchParams({
    limit: String(options.limit ?? 20),
    offset: String(options.offset ?? 0),
    sort_order: filters.sortOrder,
  });
  if (filters.directionId) params.set("direction_id", filters.directionId);
  if (filters.entityType) params.set("entity_type", filters.entityType);
  filters.decisionTypes.forEach((decisionType) =>
    params.append("decision_types", decisionType),
  );
  filters.decisionSources.forEach((decisionSource) =>
    params.append("decision_sources", decisionSource),
  );
  if (filters.isAuditSample !== null)
    params.set("is_audit_sample", String(filters.isAuditSample));
  if (filters.isReviewed !== null)
    params.set("is_reviewed", String(filters.isReviewed));
  if (filters.isOverridden !== null)
    params.set("is_overridden", String(filters.isOverridden));
  if (filters.createdFrom) params.set("created_from", filters.createdFrom);
  if (filters.createdTo) params.set("created_to", filters.createdTo);
  return params;
}

function personalReviewSearchParams(
  filters: PersonalReviewFilters,
  options: { limit?: number; offset?: number } = {},
) {
  const params = new URLSearchParams({
    limit: String(options.limit ?? 20),
    offset: String(options.offset ?? 0),
    due_only: String(filters.dueOnly),
    sort_order: filters.sortOrder,
  });
  if (filters.directionId) params.set("direction_id", filters.directionId);
  filters.statuses.forEach((status) => params.append("statuses", status));
  if (filters.dueBefore) params.set("due_before", filters.dueBefore);
  return params;
}

export const api = {
  notifications: (limit = 20, offset = 0, signal?: AbortSignal) =>
    apiRequest<NotificationPage>(
      `/api/v1/notifications?limit=${limit}&offset=${offset}`,
      { signal },
    ),
  markNotificationRead: (notificationId: string) =>
    apiRequest<void>(`/api/v1/notifications/${notificationId}/read`, {
      method: "PUT",
    }),
  markAllNotificationsRead: () =>
    apiRequest<void>("/api/v1/notifications/read-all", { method: "PUT" }),
  me: () => apiRequest<User>("/api/v1/me"),
  updateMyEmail: (email: string) =>
    apiRequest<User>("/api/v1/me/email", {
      method: "PATCH",
      body: JSON.stringify({ email }),
    }),
  myPayments: () => apiRequest<StudentPaymentDashboard>("/api/v1/payments/me"),
  updateMyPaymentDays: (paymentDays: number[]) =>
    apiRequest<StudentPaymentDashboard>("/api/v1/payments/me/schedule", {
      method: "PUT",
      body: JSON.stringify({ payment_days: paymentDays }),
    }),
  createPaymentLink: (installmentId: string) =>
    apiRequest<PaymentLinkRead>(
      `/api/v1/payments/installments/${installmentId}/link`,
      { method: "POST" },
    ),
  mentorStudentPayments: (studentId: string) =>
    apiRequest<StudentPaymentDashboard>(
      `/api/v1/mentor/students/${studentId}/payments`,
    ),
  setMentorStudentEmployment: (
    studentId: string,
    payload: EmploymentMutation,
  ) =>
    apiRequest<StudentPaymentDashboard>(
      `/api/v1/mentor/students/${studentId}/employment`,
      { method: "PUT", body: JSON.stringify(payload) },
    ),
  terminateMentorStudentEmployment: (
    studentId: string,
    payload: { ended_at: string; reason: string | null },
  ) =>
    apiRequest<StudentPaymentDashboard>(
      `/api/v1/mentor/students/${studentId}/employment/terminate`,
      { method: "POST", body: JSON.stringify(payload) },
    ),
  mentorRewards: () =>
    apiRequest<MentorRewardSummary>("/api/v1/mentor/rewards"),
  requestMentorPayout: (amountRubles: number) =>
    apiRequest<MentorRewardSummary>("/api/v1/mentor/payouts", {
      method: "POST",
      body: JSON.stringify({ amount_rubles: amountRubles }),
    }),
  cancelMentorPayout: (payoutId: string, reason: string | null = null) =>
    apiRequest<MentorRewardSummary>(
      `/api/v1/mentor/payouts/${payoutId}/cancel`,
      { method: "POST", body: JSON.stringify({ reason }) },
    ),
  uploadMentorPayoutReceipt: (
    payoutId: string,
    file: File,
    options?: UploadOptions,
  ) =>
    uploadFile<MentorRewardSummary>(
      `/api/v1/mentor/payouts/${payoutId}/receipt/upload`,
      `/api/v1/mentor/payouts/${payoutId}/receipt/complete`,
      file,
      {},
      options,
    ),
  openMentorPayoutReceipt: (payoutId: string) =>
    apiRequest<InterviewDownloadUrl>(
      `/api/v1/mentor/payouts/${payoutId}/receipt`,
    ).then((result) => result.url),
  deleteMentorPayoutReceipt: (payoutId: string) =>
    apiRequest<MentorRewardSummary>(
      `/api/v1/mentor/payouts/${payoutId}/receipt`,
      { method: "DELETE" },
    ),
  adminPayments: (options: {
    status?: PaymentInstallmentStatus | null;
    limit?: number;
    offset?: number;
  }) => {
    const params = new URLSearchParams({
      limit: String(options.limit ?? 50),
      offset: String(options.offset ?? 0),
    });
    if (options.status) params.set("status", options.status);
    return apiRequest<AdminPaymentPage>(
      `/api/v1/admin/payments?${params.toString()}`,
    );
  },
  adminPaymentStudents: (
    options: {
      status?: AdminEmploymentPaymentStatus;
      limit?: number;
      offset?: number;
    } = {},
  ) =>
    apiRequest<AdminPaymentStudentPage>(
      `/api/v1/admin/payments/students?status=${options.status ?? "outstanding"}&limit=${options.limit ?? 50}&offset=${options.offset ?? 0}`,
    ),
  adminPaymentStudent: (studentId: string) =>
    apiRequest<StudentPaymentDashboard>(
      `/api/v1/admin/payments/students/${studentId}`,
    ),
  adminTochkaTestPayment: () =>
    apiRequest<AdminTochkaTestPaymentRead | null>(
      "/api/v1/admin/payments/tochka/test-payment",
    ),
  createAdminTochkaTestPayment: (email: string) =>
    apiRequest<AdminTochkaTestPaymentRead>(
      "/api/v1/admin/payments/tochka/test-payment",
      { method: "POST", body: JSON.stringify({ email }) },
    ),
  adminOverduePayments: (options: { limit?: number; offset?: number } = {}) =>
    apiRequest<AdminPaymentPage>(
      `/api/v1/admin/payments/overdue?limit=${options.limit ?? 50}&offset=${options.offset ?? 0}`,
    ),
  updateAdminPaymentDays: (studentId: string, paymentDays: number[]) =>
    apiRequest<StudentPaymentDashboard>(
      `/api/v1/admin/payments/students/${studentId}/schedule`,
      {
        method: "PUT",
        body: JSON.stringify({ payment_days: paymentDays }),
      },
    ),
  rescheduleAdminPayment: (
    installmentId: string,
    payload: { due_date: string; reason: string },
  ) =>
    apiRequest<StudentPaymentDashboard>(
      `/api/v1/admin/payments/installments/${installmentId}/due-date`,
      { method: "PATCH", body: JSON.stringify(payload) },
    ),
  confirmAdminPayment: (installmentId: string) =>
    apiRequest<StudentPaymentDashboard>(
      `/api/v1/admin/payments/installments/${installmentId}/confirm`,
      { method: "POST" },
    ),
  revokeAdminPayment: (installmentId: string, reason: string) =>
    apiRequest<StudentPaymentDashboard>(
      `/api/v1/admin/payments/installments/${installmentId}/revoke`,
      { method: "POST", body: JSON.stringify({ reason }) },
    ),
  markAdminMentorRewardPaid: (rewardId: string) =>
    apiRequest<void>(`/api/v1/admin/payments/rewards/${rewardId}/mark-paid`, {
      method: "POST",
    }),
  voidAdminMentorReward: (rewardId: string, reason: string) =>
    apiRequest<AdminMentorPayoutDashboard>(
      `/api/v1/admin/payments/rewards/${rewardId}/void`,
      { method: "POST", body: JSON.stringify({ reason }) },
    ),
  adminMentorPayouts: () =>
    apiRequest<AdminMentorPayoutDashboard>(
      "/api/v1/admin/payments/mentor-payouts",
    ),
  adminMentorPayoutDetail: (mentorId: string) =>
    apiRequest<AdminMentorPayoutDetail>(
      `/api/v1/admin/payments/mentors/${mentorId}`,
    ),
  createAdminMentorPayout: (
    mentorId: string,
    payload: { amount_rubles: number; payment_reference: string | null },
  ) =>
    apiRequest<AdminMentorPayoutDashboard>(
      `/api/v1/admin/payments/mentors/${mentorId}/payouts`,
      { method: "POST", body: JSON.stringify(payload) },
    ),
  markAdminMentorPayoutPaid: (
    payoutId: string,
    paymentReference: string | null,
  ) =>
    apiRequest<AdminMentorPayoutDashboard>(
      `/api/v1/admin/payments/payouts/${payoutId}/mark-paid`,
      {
        method: "POST",
        body: JSON.stringify({ payment_reference: paymentReference }),
      },
    ),
  editAdminMentorPayout: (
    payoutId: string,
    payload: {
      amount_rubles: number;
      payment_reference: string | null;
      paid_at: string | null;
      reason: string;
    },
  ) =>
    apiRequest<AdminMentorPayoutDashboard>(
      `/api/v1/admin/payments/payouts/${payoutId}`,
      { method: "PATCH", body: JSON.stringify(payload) },
    ),
  cancelAdminMentorPayout: (payoutId: string, reason: string | null = null) =>
    apiRequest<AdminMentorPayoutDashboard>(
      `/api/v1/admin/payments/payouts/${payoutId}/cancel`,
      { method: "POST", body: JSON.stringify({ reason }) },
    ),
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
  adminInterviewCardDuplicates: (
    options: {
      directionId?: string | null;
      minimumSimilarity?: number;
      limit?: number;
      offset?: number;
    } = {},
  ) => {
    const params = new URLSearchParams({
      minimum_similarity: String(options.minimumSimilarity ?? 0.35),
      limit: String(options.limit ?? 20),
      offset: String(options.offset ?? 0),
    });
    if (options.directionId) params.set("direction_id", options.directionId);
    return apiRequest<InterviewCardDuplicatePage>(
      `/api/v1/admin/card-automation/duplicates?${params.toString()}`,
    );
  },
  refreshAdminInterviewCardDuplicates: () =>
    apiRequest<InterviewCardDuplicateRefreshRead>(
      "/api/v1/admin/card-automation/duplicates/refresh",
      { method: "POST" },
    ),
  dismissAdminInterviewCardDuplicate: (
    payload: InterviewCardDuplicateMutation,
    idempotencyKey: string,
  ) =>
    apiRequest<InterviewCardDuplicateReviewResult>(
      "/api/v1/admin/card-automation/duplicates/dismiss",
      {
        method: "POST",
        headers: { "Idempotency-Key": idempotencyKey },
        body: JSON.stringify(payload),
      },
    ),
  mergeAdminInterviewCardDuplicate: (
    payload: InterviewCardDuplicateMergeMutation,
    idempotencyKey: string,
  ) =>
    apiRequest<InterviewCardDuplicateReviewResult>(
      "/api/v1/admin/card-automation/duplicates/merge",
      {
        method: "POST",
        headers: { "Idempotency-Key": idempotencyKey },
        body: JSON.stringify(payload),
      },
    ),
  adminCardAutomationClusters: (
    filters: QuestionClusterFilters,
    options: { limit?: number; offset?: number } = {},
  ) => {
    const params = questionClusterSearchParams(filters, options);
    return apiRequest<QuestionClusterPage>(
      `/api/v1/admin/card-automation/clusters?${params.toString()}`,
    );
  },
  mentorCardAutomationClusters: (
    filters: QuestionClusterFilters,
    options: { limit?: number; offset?: number } = {},
  ) => {
    const params = questionClusterSearchParams(filters, options);
    return apiRequest<QuestionClusterPage>(
      `/api/v1/mentor/card-automation/clusters?${params.toString()}`,
    );
  },
  adminCardAutomationCluster: (clusterId: string) =>
    apiRequest<QuestionClusterDetail>(
      `/api/v1/admin/card-automation/clusters/${clusterId}`,
    ),
  mentorCardAutomationCluster: (clusterId: string) =>
    apiRequest<QuestionClusterDetail>(
      `/api/v1/mentor/card-automation/clusters/${clusterId}`,
    ),
  generateAdminCardAutomationClusterAnswer: (
    clusterId: string,
    payload: QuestionClusterAnswerGenerationMutation,
    idempotencyKey: string,
  ) =>
    apiRequest<QuestionClusterAnswerGenerationResult>(
      `/api/v1/admin/card-automation/clusters/${clusterId}/generate-answer`,
      {
        method: "POST",
        headers: { "Idempotency-Key": idempotencyKey },
        body: JSON.stringify(payload),
      },
    ),
  linkAdminCardAutomationCluster: (
    clusterId: string,
    payload: QuestionClusterLinkCardMutation,
    idempotencyKey: string,
  ) =>
    apiRequest<QuestionClusterActionResult>(
      `/api/v1/admin/card-automation/clusters/${clusterId}/link-card`,
      {
        method: "POST",
        headers: { "Idempotency-Key": idempotencyKey },
        body: JSON.stringify(payload),
      },
    ),
  createCardFromAdminCardAutomationCluster: (
    clusterId: string,
    payload: QuestionClusterCreateCardMutation,
    idempotencyKey: string,
  ) =>
    apiRequest<QuestionClusterActionResult>(
      `/api/v1/admin/card-automation/clusters/${clusterId}/create-card`,
      {
        method: "POST",
        headers: { "Idempotency-Key": idempotencyKey },
        body: JSON.stringify(payload),
      },
    ),
  updateAdminCardAutomationClusterDraft: (
    clusterId: string,
    payload: QuestionClusterDraftMutation,
    idempotencyKey: string,
  ) =>
    apiRequest<QuestionClusterActionResult>(
      `/api/v1/admin/card-automation/clusters/${clusterId}/draft`,
      {
        method: "PATCH",
        headers: { "Idempotency-Key": idempotencyKey },
        body: JSON.stringify(payload),
      },
    ),
  updateMentorCardAutomationClusterDraft: (
    clusterId: string,
    payload: QuestionClusterDraftMutation,
    idempotencyKey: string,
  ) =>
    apiRequest<QuestionClusterActionResult>(
      `/api/v1/mentor/card-automation/clusters/${clusterId}/draft`,
      {
        method: "PATCH",
        headers: { "Idempotency-Key": idempotencyKey },
        body: JSON.stringify(payload),
      },
    ),
  splitAdminCardAutomationCluster: (
    clusterId: string,
    payload: QuestionClusterSplitMutation,
    idempotencyKey: string,
  ) =>
    apiRequest<QuestionClusterActionResult>(
      `/api/v1/admin/card-automation/clusters/${clusterId}/split`,
      {
        method: "POST",
        headers: { "Idempotency-Key": idempotencyKey },
        body: JSON.stringify(payload),
      },
    ),
  mergeAdminCardAutomationCluster: (
    clusterId: string,
    payload: QuestionClusterMergeMutation,
    idempotencyKey: string,
  ) =>
    apiRequest<QuestionClusterActionResult>(
      `/api/v1/admin/card-automation/clusters/${clusterId}/merge`,
      {
        method: "POST",
        headers: { "Idempotency-Key": idempotencyKey },
        body: JSON.stringify(payload),
      },
    ),
  setAdminCardAutomationClusterState: (
    clusterId: string,
    action: "ignore" | "defer" | "mark-important" | "reopen",
    payload: QuestionClusterVersionMutation,
    idempotencyKey: string,
  ) =>
    apiRequest<QuestionClusterActionResult>(
      `/api/v1/admin/card-automation/clusters/${clusterId}/${action}`,
      {
        method: "POST",
        headers: { "Idempotency-Key": idempotencyKey },
        body: JSON.stringify(payload),
      },
    ),
  setMentorCardAutomationClusterState: (
    clusterId: string,
    action: "ignore" | "defer" | "mark-important" | "reopen",
    payload: QuestionClusterVersionMutation,
    idempotencyKey: string,
  ) =>
    apiRequest<QuestionClusterActionResult>(
      `/api/v1/mentor/card-automation/clusters/${clusterId}/${action}`,
      {
        method: "POST",
        headers: { "Idempotency-Key": idempotencyKey },
        body: JSON.stringify(payload),
      },
    ),
  reprocessAdminCardAutomationOccurrence: (
    occurrenceId: string,
    payload: QuestionOccurrenceReprocessMutation,
    idempotencyKey: string,
  ) =>
    apiRequest<QuestionOccurrenceReprocessResult>(
      `/api/v1/admin/card-automation/occurrences/${occurrenceId}/reprocess`,
      {
        method: "POST",
        headers: { "Idempotency-Key": idempotencyKey },
        body: JSON.stringify(payload),
      },
    ),
  reprocessMentorCardAutomationOccurrence: (
    occurrenceId: string,
    payload: QuestionOccurrenceReprocessMutation,
    idempotencyKey: string,
  ) =>
    apiRequest<QuestionOccurrenceReprocessResult>(
      `/api/v1/mentor/card-automation/occurrences/${occurrenceId}/reprocess`,
      {
        method: "POST",
        headers: { "Idempotency-Key": idempotencyKey },
        body: JSON.stringify(payload),
      },
    ),
  bulkAdminCardAutomationClusters: (
    payload: QuestionClusterBulkMutation,
    idempotencyKey: string,
  ) =>
    apiRequest<QuestionClusterBulkResult>(
      "/api/v1/admin/card-automation/clusters/bulk",
      {
        method: "POST",
        headers: { "Idempotency-Key": idempotencyKey },
        body: JSON.stringify(payload),
      },
    ),
  adminCardAutomationDecisions: (
    filters: AutomationDecisionFilters,
    options: { limit?: number; offset?: number } = {},
  ) => {
    const params = automationDecisionSearchParams(filters, options);
    return apiRequest<AutomationDecisionPage>(
      `/api/v1/admin/card-automation/decisions?${params.toString()}`,
    );
  },
  mentorCardAutomationDecisions: (
    filters: AutomationDecisionFilters,
    options: { limit?: number; offset?: number } = {},
  ) => {
    const params = automationDecisionSearchParams(filters, options);
    return apiRequest<AutomationDecisionPage>(
      `/api/v1/mentor/card-automation/decisions?${params.toString()}`,
    );
  },
  reviewAdminCardAutomationDecision: (
    decisionId: string,
    payload: AutomationDecisionReviewMutation,
    idempotencyKey: string,
  ) =>
    apiRequest<AutomationDecisionRead>(
      `/api/v1/admin/card-automation/decisions/${decisionId}/review`,
      {
        method: "POST",
        headers: { "Idempotency-Key": idempotencyKey },
        body: JSON.stringify(payload),
      },
    ),
  reviewMentorCardAutomationDecision: (
    decisionId: string,
    payload: AutomationDecisionReviewMutation,
    idempotencyKey: string,
  ) =>
    apiRequest<AutomationDecisionRead>(
      `/api/v1/mentor/card-automation/decisions/${decisionId}/review`,
      {
        method: "POST",
        headers: { "Idempotency-Key": idempotencyKey },
        body: JSON.stringify(payload),
      },
    ),
  overrideAdminCardAutomationDecision: (
    decisionId: string,
    payload: AutomationDecisionOverrideMutation,
    idempotencyKey: string,
  ) =>
    apiRequest<AutomationDecisionRead>(
      `/api/v1/admin/card-automation/decisions/${decisionId}/override`,
      {
        method: "POST",
        headers: { "Idempotency-Key": idempotencyKey },
        body: JSON.stringify(payload),
      },
    ),
  overrideMentorCardAutomationDecision: (
    decisionId: string,
    payload: AutomationDecisionOverrideMutation,
    idempotencyKey: string,
  ) =>
    apiRequest<AutomationDecisionRead>(
      `/api/v1/mentor/card-automation/decisions/${decisionId}/override`,
      {
        method: "POST",
        headers: { "Idempotency-Key": idempotencyKey },
        body: JSON.stringify(payload),
      },
    ),
  adminCardAutomationMetrics: (filters: CardAutomationMetricsFilters) => {
    const params = new URLSearchParams({
      period_from: filters.periodFrom,
      period_to: filters.periodTo,
    });
    if (filters.directionId) params.set("direction_id", filters.directionId);
    return apiRequest<CardAutomationMetricsRead>(
      `/api/v1/admin/card-automation/metrics?${params.toString()}`,
    );
  },
  adminCardAutomationSettings: () =>
    apiRequest<CardAutomationSettingsPage>(
      "/api/v1/admin/card-automation/settings",
    ),
  updateAdminCardAutomationSettings: (
    payload: CardAutomationSettingsMutation,
    idempotencyKey: string,
  ) =>
    apiRequest<CardAutomationSettingsRead>(
      "/api/v1/admin/card-automation/settings",
      {
        method: "PUT",
        body: JSON.stringify(payload),
        headers: { "Idempotency-Key": idempotencyKey },
      },
    ),
  personalReviewItems: (
    filters: PersonalReviewFilters,
    options: { limit?: number; offset?: number } = {},
  ) => {
    const params = personalReviewSearchParams(filters, options);
    return apiRequest<PersonalReviewItemPage>(
      `/api/v1/students/me/personal-review-items?${params.toString()}`,
    );
  },
  adminManagedPersonalReviewItems: (
    studentId: string,
    filters: PersonalReviewFilters,
    options: { limit?: number; offset?: number } = {},
  ) => {
    const params = personalReviewSearchParams(filters, options);
    return apiRequest<PersonalReviewItemPage>(
      `/api/v1/admin/card-automation/students/${studentId}/personal-review-items?${params.toString()}`,
    );
  },
  mentorManagedPersonalReviewItems: (
    studentId: string,
    filters: PersonalReviewFilters,
    options: { limit?: number; offset?: number } = {},
  ) => {
    const params = personalReviewSearchParams(filters, options);
    return apiRequest<PersonalReviewItemPage>(
      `/api/v1/mentor/card-automation/students/${studentId}/personal-review-items?${params.toString()}`,
    );
  },
  updateAdminManagedPersonalReviewItem: (
    studentId: string,
    itemId: string,
    payload: ManagedPersonalReviewMutation,
    idempotencyKey: string,
  ) =>
    apiRequest<ManagedPersonalReviewResult>(
      `/api/v1/admin/card-automation/students/${studentId}/personal-review-items/${itemId}`,
      {
        method: "PATCH",
        headers: { "Idempotency-Key": idempotencyKey },
        body: JSON.stringify(payload),
      },
    ),
  updateMentorManagedPersonalReviewItem: (
    studentId: string,
    itemId: string,
    payload: ManagedPersonalReviewMutation,
    idempotencyKey: string,
  ) =>
    apiRequest<ManagedPersonalReviewResult>(
      `/api/v1/mentor/card-automation/students/${studentId}/personal-review-items/${itemId}`,
      {
        method: "PATCH",
        headers: { "Idempotency-Key": idempotencyKey },
        body: JSON.stringify(payload),
      },
    ),
  reviewPersonalReviewItem: (
    itemId: string,
    payload: PersonalReviewMutation,
    idempotencyKey: string,
  ) =>
    apiRequest<PersonalReviewResult>(
      `/api/v1/students/me/personal-review-items/${itemId}/review`,
      {
        method: "POST",
        headers: { "Idempotency-Key": idempotencyKey },
        body: JSON.stringify(payload),
      },
    ),
  adminCompanyAliasProposals: (
    options: {
      status?: "all" | "pending" | "approved" | "rejected";
      q?: string;
      limit?: number;
      offset?: number;
    } = {},
  ) => {
    const params = new URLSearchParams({
      status: options.status ?? "pending",
      limit: String(options.limit ?? 20),
      offset: String(options.offset ?? 0),
    });
    if (options.q) params.set("q", options.q);
    return apiRequest<AdminCompanyAliasProposalPage>(
      `/api/v1/admin/interviews/company-alias-proposals?${params.toString()}`,
    );
  },
  moderateCompanyAliasProposal: (
    proposalId: string,
    payload: AdminCompanyAliasProposalMutation,
  ) =>
    apiRequest<AdminCompanyAliasProposalRead>(
      `/api/v1/admin/interviews/company-alias-proposals/${proposalId}`,
      { method: "PATCH", body: JSON.stringify(payload) },
    ),
  intelligenceInterview: (id: string) =>
    apiRequest<IntelligenceInterviewDetail>(`/api/v1/interviews/${id}`),
  intelligenceInterviewProcessing: (id: string) =>
    apiRequest<IntelligenceProcessing>(`/api/v1/interviews/${id}/processing`),
  adminIntelligenceOperations: () =>
    apiRequest<AdminIntelligenceOperations>(
      "/api/v1/admin/interviews/ai-operations",
    ),
  adminRequeueIntelligenceInterview: (id: string) =>
    apiRequest<IntelligenceInterviewDetail>(
      `/api/v1/admin/interviews/ai-operations/${id}/requeue`,
      { method: "POST" },
    ),
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
    reviewStatus:
      "requested" | "needs_review" | "reviewed" | "processing" | "all",
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
      deck_id?: string;
      category?: string;
      create_category?: boolean;
      frequency?: "frequent" | "occasional";
      target_card_id?: string;
      create_new_card?: boolean;
      frequency_mode?: "automatic" | "manual";
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
    group_calendars: Array<{ track_id: string; calendar_url: string }>;
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
      sort?: MentorStudentSort;
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
    if (options.sort) params.set("sort", options.sort);
    return apiRequest<MentorStudentPage>(`/api/v1/mentor/students?${params}`);
  },
  mentorStudent: (id: string) =>
    apiRequest<MentorStudentDetail>(`/api/v1/mentor/students/${id}`),
  mentorInterviewAnalytics: (options: {
    period: MentorAnalyticsPeriod;
    trackId?: string | null;
    mentorId?: string | null;
    withoutMentor?: boolean;
    isActive?: boolean | null;
    learningStatuses?: StudentLearningStatus[];
  }) => {
    const params = new URLSearchParams({ period: options.period });
    if (options.trackId) params.set("track_id", options.trackId);
    if (options.mentorId) params.set("mentor_id", options.mentorId);
    if (options.withoutMentor) params.set("without_mentor", "true");
    if (options.isActive !== undefined && options.isActive !== null) {
      params.set("is_active", String(options.isActive));
    }
    options.learningStatuses?.forEach((status) =>
      params.append("learning_status", status),
    );
    return apiRequest<MentorInterviewAnalytics>(
      `/api/v1/mentor/students/analytics?${params}`,
    );
  },
  mentorEfficiencyAnalytics: (options: {
    period: MentorAnalyticsPeriod;
    trackId?: string | null;
    isActive?: boolean | null;
  }) => {
    const params = new URLSearchParams({ period: options.period });
    if (options.trackId) params.set("track_id", options.trackId);
    if (options.isActive !== undefined && options.isActive !== null) {
      params.set("is_active", String(options.isActive));
    }
    return apiRequest<MentorEfficiencyAnalytics>(
      `/api/v1/mentor/students/mentor-efficiency?${params}`,
    );
  },
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
    options?: UploadOptions,
  ) =>
    uploadFile<MentorDocumentRead>(
      `/api/v1/mentor/students/${studentId}/documents/${kind}/upload`,
      `/api/v1/mentor/students/${studentId}/documents/${kind}/complete`,
      file,
      {},
      options,
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
    uploadFile<MockInterviewRead>(
      `/api/v1/mentor/students/${studentId}/mock-interviews/${mockId}/media/upload`,
      `/api/v1/mentor/students/${studentId}/mock-interviews/${mockId}/media/complete`,
      file,
      {},
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
  adminApplications: (
    options: {
      query?: string;
      statuses?: string[];
      limit?: number;
      offset?: number;
    } = {},
  ) => {
    const params = new URLSearchParams({
      limit: String(options.limit ?? 50),
      offset: String(options.offset ?? 0),
    });
    if (options.query) params.set("q", options.query);
    options.statuses?.forEach((status) => params.append("status", status));
    return apiRequest<OnboardingApplicationPage>(
      `/api/v1/admin/applications?${params}`,
    );
  },
  adminApplication: (applicantId: string) =>
    apiRequest<OnboardingApplicationDetail>(
      `/api/v1/admin/applications/${applicantId}`,
    ),
  executeAdminApplicationAction: (
    applicantId: string,
    action: OnboardingApplicationAction,
    comment?: string | null,
  ) =>
    apiRequest<OnboardingApplicationActionResponse>(
      `/api/v1/admin/applications/${applicantId}/actions`,
      {
        method: "POST",
        body: JSON.stringify({ action, comment: comment ?? null }),
      },
    ),
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
    uploadFile<ProtectedContentMediaRead>(
      `/api/v1/admin/roadmaps/${roadmapId}/sections/${sectionId}/topics/${topicId}/media/upload-url`,
      `/api/v1/admin/roadmaps/${roadmapId}/sections/${sectionId}/topics/${topicId}/media/finalize`,
      file,
      { title: metadata.title, position: metadata.position },
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
  deleteAdminRoadmap: (id: string) =>
    apiRequest<void>(`/api/v1/admin/roadmaps/${id}`, { method: "DELETE" }),
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
    uploadFile<ProtectedContentMediaRead>(
      `/api/v1/admin/knowledge/topics/${topicId}/entries/${entryId}/media/upload-url`,
      `/api/v1/admin/knowledge/topics/${topicId}/entries/${entryId}/media/finalize`,
      file,
      { title: metadata.title, position: metadata.position },
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
  retryAdminContentMediaNormalization: (mediaId: string) =>
    apiRequest<ProtectedContentMediaRead>(
      `/api/v1/admin/content-media/${mediaId}/normalization/retry`,
      { method: "POST" },
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
  interviewSession: (deckSlug: string, frequentOnly = false) => {
    const params = new URLSearchParams();
    if (frequentOnly) params.set("frequent_only", "true");
    const suffix = params.size > 0 ? `?${params.toString()}` : "";
    return apiRequest<InterviewStudySession>(
      `/api/v1/interviews/decks/${deckSlug}/session${suffix}`,
    );
  },
  searchInterviewCards: (
    deckSlug: string,
    query: string,
    frequentOnly = false,
  ) => {
    const params = new URLSearchParams({ query });
    if (frequentOnly) params.set("frequent_only", "true");
    return apiRequest<InterviewStudySession["cards"]>(
      `/api/v1/interviews/decks/${deckSlug}/cards/search?${params.toString()}`,
    );
  },
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
  deleteInterviewProcess: (id: string) =>
    apiRequest<void>(`/api/v1/interviews/journal/tracks/${id}`, {
      method: "DELETE",
    }),
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
    uploadFile<InterviewProcessDetail>(
      `/api/v1/interviews/journal/tracks/${processId}/stages/${stageId}/media/upload`,
      `/api/v1/interviews/journal/tracks/${processId}/stages/${stageId}/media/complete`,
      file,
      {},
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
    options?: UploadOptions,
  ) =>
    uploadFile<InterviewProcessDetail>(
      `/api/v1/interviews/journal/tracks/${processId}/stages/${stageId}/attachments/upload`,
      `/api/v1/interviews/journal/tracks/${processId}/stages/${stageId}/attachments/complete`,
      file,
      {},
      options,
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
  uploadInterviewOffer: (
    processId: string,
    file: File,
    options?: UploadOptions,
  ) =>
    uploadFile<InterviewProcessDetail>(
      `/api/v1/interviews/journal/tracks/${processId}/offer/upload`,
      `/api/v1/interviews/journal/tracks/${processId}/offer/complete`,
      file,
      {},
      options,
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
    if (filters.hasAiReview) params.set("has_ai_review", "true");
    if (filters.favoritesOnly) params.set("favorites_only", "true");
    if (filters.recruiterUsername)
      params.set("recruiter_username", filters.recruiterUsername);
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
    if (filters.hasAiReview) params.set("has_ai_review", "true");
    if (filters.favoritesOnly) params.set("favorites_only", "true");
    if (filters.recruiterUsername)
      params.set("recruiter_username", filters.recruiterUsername);
    const query = params.toString();
    return apiRequest<InterviewCatalogCompanyDetail>(
      `/api/v1/interviews/catalog/companies/${companyId}${query ? `?${query}` : ""}`,
    );
  },
  favoriteInterviewCatalogStage: (stageId: string) =>
    apiRequest<void>(`/api/v1/interviews/catalog/stages/${stageId}/favorite`, {
      method: "PUT",
    }),
  unfavoriteInterviewCatalogStage: (stageId: string) =>
    apiRequest<void>(`/api/v1/interviews/catalog/stages/${stageId}/favorite`, {
      method: "DELETE",
    }),
  markInterviewCatalogStageViewed: (stageId: string) =>
    apiRequest<void>(`/api/v1/interviews/catalog/stages/${stageId}/view`, {
      method: "PUT",
    }),
  interviewCatalogHistory: (
    options: { limit?: number; offset?: number } = {},
  ) => {
    const params = new URLSearchParams({
      limit: String(options.limit ?? 50),
      offset: String(options.offset ?? 0),
    });
    return apiRequest<InterviewCatalogHistoryPage>(
      `/api/v1/interviews/catalog/history?${params.toString()}`,
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
  interviewRecruiters: (
    filters: {
      query: string;
      trackId: string | null;
      contacted: boolean | null;
      sort: RecruiterSort;
    },
    options: { limit?: number; offset?: number } = {},
  ) => {
    const params = new URLSearchParams({
      limit: String(options.limit ?? 24),
      offset: String(options.offset ?? 0),
    });
    if (filters.query) params.set("q", filters.query);
    if (filters.trackId) params.set("track_id", filters.trackId);
    if (filters.contacted !== null)
      params.set("contacted", String(filters.contacted));
    params.set("sort", filters.sort);
    return apiRequest<RecruiterContactPage>(
      `/api/v1/interviews/recruiters?${params.toString()}`,
    );
  },
  openRecruiterContact: (recruiterId: string) =>
    apiRequest<RecruiterContactOpenRead>(
      `/api/v1/interviews/recruiters/${recruiterId}/contact`,
      { method: "POST" },
    ),
  setRecruiterFeedback: (
    recruiterId: string,
    payload: RecruiterFeedbackMutation,
  ) =>
    apiRequest<RecruiterFeedbackRead>(
      `/api/v1/interviews/recruiters/${recruiterId}/feedback`,
      { method: "PUT", body: JSON.stringify(payload) },
    ),
  deleteRecruiterFeedback: (recruiterId: string) =>
    apiRequest<void>(`/api/v1/interviews/recruiters/${recruiterId}/feedback`, {
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
  deleteAdminInterviewProcess: (id: string) =>
    apiRequest<void>(`/api/v1/admin/interviews/processes/${id}`, {
      method: "DELETE",
    }),
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
