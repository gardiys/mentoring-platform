import type { components } from "../api/generated/schema";
import type { StorageUploadIntent } from "../api/client";

type Schemas = components["schemas"];

export type ContentMediaKind = "audio" | "video";
export type ContentMediaProcessingStatus =
  "queued" | "processing" | "ready" | "failed";

export interface ProtectedContentMediaRead {
  id: string;
  kind: ContentMediaKind;
  filename: string;
  content_type: string;
  size: number;
  title: string | null;
  position: number;
  processing_status: ContentMediaProcessingStatus;
  playback_available: boolean;
  normalization_attempts: number;
  normalization_started_at: string | null;
  normalization_completed_at: string | null;
  normalization_error_code: string | null;
  normalization_error_message: string | null;
  created_at: string;
}

export type ContentMediaUploadIntent = StorageUploadIntent;

export interface ContentMediaUploadMetadata {
  title: string | null;
  position: number;
}

export interface ContentMediaPlayback {
  url: string;
  expires_in: number;
}

export type User = Schemas["UserRead"];
export type RoadmapListItem = Schemas["RoadmapListItem"];
export type RoadmapDetail = Schemas["RoadmapDetail"];
export type TopicDetail = Schemas["TopicDetail"] & {
  media: ProtectedContentMediaRead[];
};
export type ProgressStatus = Schemas["TopicProgressRead"]["status"];
export type ProgressUpdateResponse = Schemas["ProgressUpdateResponse"];
export type AdminRoadmapCreate = Schemas["AdminRoadmapCreate"];
export type AdminSectionCreate = Schemas["AdminSectionCreate"];
export type AdminTopicCreate = Schemas["AdminTopicCreate"];
export type AdminRoadmapRead = Schemas["AdminRoadmapRead"];
export type AdminRoadmapUpdate = Schemas["AdminRoadmapUpdate"];
export type AdminSectionUpdate = Schemas["AdminSectionUpdate"];
export type AdminTopicUpdate = Schemas["AdminTopicUpdate"];
export type AdminRoadmapSummary = Schemas["AdminRoadmapSummary"];
export type AdminRoadmapOutline = Schemas["AdminRoadmapOutline"];
export type AdminRoadmapSettingsMutation =
  Schemas["AdminRoadmapSettingsMutation"];
export type AdminSectionMutation = Schemas["AdminSectionMutation"];
export type AdminSectionOutline = Schemas["AdminSectionOutline"];
export type AdminTopicRead = Schemas["AdminTopicRead"] & {
  media: ProtectedContentMediaRead[];
};
export type AdminTrackMutation = Schemas["AdminTrackMutation"];
export type AdminTrackRead = Schemas["AdminTrackRead"];
export type AdminTrackOptions = Schemas["AdminTrackOptions"];
export type AdminTrackRoadmapRead = Schemas["AdminTrackRoadmapRead"];
export type AdminTrackStudentOption = Schemas["AdminTrackStudentOption"];
export type TrackAccessRead = Schemas["TrackAccessRead"];

export type AdminStudentMutation = Omit<
  Schemas["AdminStudentMutation"],
  | "telegram_username"
  | "last_name"
  | "email"
  | "track_ids"
  | "mentor_id"
  | "repayment_percent"
  | "mentor_reward_percent"
  | "entry_payment_rubles"
  | "entry_payment_paid"
  | "program_excluded"
  | "program_exclusion_reason"
> & {
  telegram_username: string | null;
  last_name: string | null;
  email: string | null;
  track_ids: string[];
  mentor_id: string | null;
  repayment_percent: number;
  mentor_reward_percent: number | null;
  entry_payment_rubles: number;
  entry_payment_paid: boolean;
  program_excluded: boolean;
  program_exclusion_reason: string | null;
};
export type AdminStudentTrackRead = Schemas["AdminStudentTrackRead"];
export interface AdminStudentMentorRead {
  id: string;
  role: Schemas["UserRole"];
  first_name: string;
  last_name: string | null;
  telegram_username: string | null;
}
export type AdminStudentListItem = Omit<
  Schemas["AdminStudentListItem"],
  | "telegram_username"
  | "mentor"
  | "learning_status"
  | "repayment_percent"
  | "mentor_reward_percent"
  | "entry_payment_kopecks"
  | "entry_payment_paid_at"
  | "program_excluded_at"
  | "program_exclusion_reason"
> & {
  telegram_username: string | null;
  mentor: AdminStudentMentorRead | null;
  learning_status: StudentLearningStatus;
  repayment_percent: number;
  mentor_reward_percent: number | null;
  entry_payment_kopecks: number;
  entry_payment_paid_at: string | null;
  program_excluded_at: string | null;
  program_exclusion_reason: string | null;
};
export type AdminStudentDetail = Omit<
  Schemas["AdminStudentDetail"],
  | "telegram_username"
  | "mentor"
  | "learning_status"
  | "repayment_percent"
  | "mentor_reward_percent"
  | "entry_payment_kopecks"
  | "entry_payment_paid_at"
  | "program_excluded_at"
  | "program_exclusion_reason"
> & {
  telegram_username: string | null;
  mentor: AdminStudentMentorRead | null;
  learning_status: StudentLearningStatus;
  repayment_percent: number;
  mentor_reward_percent: number | null;
  entry_payment_kopecks: number;
  entry_payment_paid_at: string | null;
  program_excluded_at: string | null;
  program_exclusion_reason: string | null;
};
export type AdminStudentPage = Omit<Schemas["AdminStudentPage"], "items"> & {
  items: AdminStudentListItem[];
  mentors: AdminStudentMentorRead[];
  tracks: AdminStudentTrackOption[];
};
export type AdminStudentTrackOption = Schemas["AdminStudentTrackOption"];
export type AdminStudentOptions = Schemas["AdminStudentOptions"] & {
  mentors: AdminStudentMentorRead[];
};
export type AdminMentorMutation = Schemas["AdminMentorMutation"];
export interface AdminMentorProfileMutation {
  first_name: string;
  last_name: string | null;
  email: string | null;
  telegram_username: string | null;
}
export type AdminMentorListItem = Schemas["AdminMentorListItem"];
export type AdminMentorCandidate = Schemas["AdminMentorCandidate"];
export type AdminMentorDirectionsMutation =
  Schemas["AdminMentorDirectionsMutation"];
export type AdminStudentMentorMutation = Schemas["AdminStudentMentorMutation"];
export type KnowledgeEntryKind = Schemas["KnowledgeEntryKind"];
export type KnowledgeTopicListItem = Schemas["KnowledgeTopicListItem"];
export type KnowledgeTopicDetail = Schemas["KnowledgeTopicDetail"];
export type KnowledgeEntryDetail = Schemas["KnowledgeEntryDetail"] & {
  media: ProtectedContentMediaRead[];
};
export type KnowledgeSearchResult = Schemas["KnowledgeSearchResult"];
export type AdminKnowledgeEntryMutation =
  Schemas["AdminKnowledgeEntryMutation"];
export type AdminKnowledgeTopicMutation =
  Schemas["AdminKnowledgeTopicMutation"];
export type AdminKnowledgeTopicRead = Schemas["AdminKnowledgeTopicRead"];
export type AdminKnowledgeEntryRead = Schemas["AdminKnowledgeEntryRead"] & {
  media: ProtectedContentMediaRead[];
};
export type AdminKnowledgeTopicSummary = Schemas["AdminKnowledgeTopicSummary"];
export type AdminKnowledgeTopicOutline = Schemas["AdminKnowledgeTopicOutline"];
export type AdminKnowledgeTopicSettingsMutation =
  Schemas["AdminKnowledgeTopicSettingsMutation"];
export type InterviewCardFrequency = Schemas["InterviewCardFrequency"];
export type InterviewReviewRating = Schemas["InterviewReviewRating"];
export type InterviewDeckListItem = Schemas["InterviewDeckListItem"];
export type InterviewStudySession = Schemas["InterviewStudySession"];
export type InterviewTopicOption = Schemas["InterviewTopicOption"];
export type InterviewReviewResult = Schemas["InterviewReviewResult"];
export type AdminInterviewCardMutation = Schemas["AdminInterviewCardMutation"];
export type AdminInterviewDeckMutation = Schemas["AdminInterviewDeckMutation"];
export type AdminInterviewDeckRead = Schemas["AdminInterviewDeckRead"];
export type AdminInterviewCardRead = Schemas["AdminInterviewCardRead"];
export type AdminInterviewCardPage = Schemas["AdminInterviewCardPage"];
export type AdminInterviewDeckSummary = Schemas["AdminInterviewDeckSummary"];
export type AdminInterviewDeckSettingsMutation =
  Schemas["AdminInterviewDeckSettingsMutation"];
export type InterviewProcessStatus = Schemas["InterviewProcessStatus"];
export type InterviewStageType = Schemas["InterviewStageType"];
export type InterviewAttachmentRead = Schemas["InterviewAttachmentRead"];
export type InterviewStageAttachmentRead =
  Schemas["InterviewStageAttachmentRead"];
export type InterviewProcessMutation = Schemas["InterviewProcessMutation"];
export type InterviewProcessOutcomeMutation =
  Schemas["InterviewProcessOutcomeMutation"];
export type InterviewProcessRecruitersMutation =
  Schemas["InterviewProcessRecruitersMutation"];
export type InterviewProcessStageMutation =
  Schemas["InterviewProcessStageMutation"];
export type InterviewProcessStageRead = Schemas["InterviewProcessStageRead"];
export type InterviewProcessSummary = Schemas["InterviewProcessSummary"];
export type AdminInterviewProcessSummary =
  Schemas["AdminInterviewProcessSummary"];
export type AdminInterviewProcessPage = Schemas["AdminInterviewProcessPage"];
export type InterviewProcessDetail = Schemas["InterviewProcessDetail"];
export type CompanyOption = Schemas["CompanyOption"];
export type InterviewDirectionOption = Schemas["InterviewDirectionOption"];
export type CompanyAliasProposalStatus = Schemas["CompanyAliasProposalStatus"];
export type AdminCompanyAliasProposalRead =
  Schemas["AdminCompanyAliasProposalRead"];
export type AdminCompanyAliasProposalPage =
  Schemas["AdminCompanyAliasProposalPage"];
export type AdminCompanyAliasProposalMutation =
  Schemas["AdminCompanyAliasProposalMutation"];
export type InterviewUploadIntent = StorageUploadIntent;
export type InterviewDownloadUrl = Schemas["InterviewDownloadUrl"];
export type InterviewCatalogCompanyListItem =
  Schemas["InterviewCatalogCompanyListItem"];
export type InterviewCatalogCompanyPage =
  Schemas["InterviewCatalogCompanyPage"];
export type InterviewCatalogCompanyDetail = Omit<
  Schemas["InterviewCatalogCompanyDetail"],
  "tracks"
> & { tracks: InterviewCatalogTrackRead[] };
export type InterviewCatalogAuthorRead = Schemas["InterviewCatalogAuthorRead"];
export type InterviewCatalogTrackRead = Omit<
  Schemas["InterviewCatalogTrackRead"],
  "stages"
> & { stages: InterviewCatalogStageRead[] };
export type InterviewCatalogStageRead = Omit<
  Schemas["InterviewCatalogStageRead"],
  "comments"
> & { comments: InterviewCatalogCommentRead[] };
export type InterviewCatalogCommentRead =
  Schemas["InterviewCatalogCommentRead"] & {
    is_mentor_feedback: boolean;
  };
export type InterviewCatalogCommentMutation =
  Schemas["InterviewCatalogCommentMutation"];
export type InterviewCatalogMediaKind = Schemas["InterviewCatalogMediaKind"];
export type InterviewCatalogHistoryItem =
  Schemas["InterviewCatalogHistoryItem"];
export type InterviewCatalogHistoryPage =
  Schemas["InterviewCatalogHistoryPage"];

export interface InterviewCatalogFilters {
  query: string;
  authorId: string | null;
  trackId: string | null;
  stageType: InterviewStageType | null;
  hasOffer: boolean;
  mediaKind: InterviewCatalogMediaKind | null;
  hasAiReview: boolean;
  favoritesOnly: boolean;
}

export type StudentLearningStatus =
  "learning" | "interviewing" | "probation" | "finished";
export type StudentAccessFilter = "all" | "active" | "blocked";
export type StudentStrengthLevel = "weak" | "medium" | "strong";
export type MentorDocumentKind = "resume" | "legend";
export type MockInterviewStatus = "planned" | "completed";

export type ScheduleEventKind = "weekly_call" | "meeting";
export type ScheduleEventSource = "mentor" | "platform";

export interface ScheduleTrackRead {
  id: string;
  slug: string;
  title: string;
}

export interface ScheduleEventRead {
  id: string;
  track: ScheduleTrackRead;
  mentor_id: string | null;
  source: ScheduleEventSource;
  source_name: string;
  kind: ScheduleEventKind;
  title: string;
  description: string | null;
  meeting_url: string | null;
  weekday: number | null;
  starts_at_time: string | null;
  timezone: string | null;
  starts_at: string | null;
  regular_next_occurrence_at: string | null;
  next_occurrence_at: string | null;
  is_rescheduled: boolean;
  rescheduled_from: string | null;
  rescheduled_to: string | null;
  created_at: string;
  updated_at: string;
}

export interface MentorProfileRead {
  mentor_id: string;
  consultation_url: string | null;
  group_calendar_url: string | null;
  tracks: ScheduleTrackRead[];
  weekly_calls: ScheduleEventRead[];
  one_off_activities: ScheduleEventRead[];
  updated_at: string | null;
}

export interface MentorWeeklyCallMutation {
  track_id: string;
  title: string;
  description: string | null;
  weekday: number;
  starts_at_time: string | null;
  timezone: string;
  meeting_url: string;
}

export interface MentorOneOffActivityMutation {
  track_id: string;
  title: string;
  description: string | null;
  starts_at: string;
  meeting_url: string | null;
}

export interface MentorWeeklyCallRescheduleMutation {
  starts_at: string;
}

export interface AdminScheduleEventMutation {
  track_id: string;
  kind: ScheduleEventKind;
  title: string;
  description: string | null;
  meeting_url: string | null;
  weekday: number | null;
  starts_at_time: string | null;
  timezone: string | null;
  starts_at: string | null;
}

export interface AdminScheduleEventPageRead {
  items: ScheduleEventRead[];
  total: number;
  limit: number;
  offset: number;
}

export interface MyMentorPublicRead {
  id: string;
  first_name: string;
  last_name: string | null;
  telegram_username: string | null;
  consultation_url: string | null;
  group_calendar_url: string | null;
}

export interface PinnedResourceLinkMutation {
  title: string;
  description: string | null;
  url: string;
  position: number;
}

export interface PinnedResourceLinkRead extends PinnedResourceLinkMutation {
  id: string;
  created_at: string;
  updated_at: string;
}

export interface MyMentorDashboardRead {
  mentor: MyMentorPublicRead | null;
  schedule: ScheduleEventRead[];
  useful_links: PinnedResourceLinkRead[];
}

export type PaymentInstallmentStatus =
  "scheduled" | "pending" | "paid" | "cancelled";
export type StudentEmploymentStatus = "active" | "terminated";
export type MentorRewardKind =
  "employment_payment" | "entry_payment" | "program_exclusion" | "legacy_fixed";
export type MentorPayoutStatus = "requested" | "paid" | "cancelled";
export type MentorPayoutOrigin = "mentor_request" | "admin_direct";

export interface EmploymentMutation {
  company_name: string;
  company_id: string | null;
  start_date: string;
  net_salary_rubles: number;
}

export interface EmploymentRead {
  id: string;
  company_id: string | null;
  company_name: string;
  start_date: string;
  net_salary_kopecks: number;
  repayment_percent: number;
  status: StudentEmploymentStatus;
  ended_at: string | null;
  end_reason: string | null;
  payment_days: number[];
  total_owed_kopecks: number;
  created_at: string;
  updated_at: string;
}

export interface PaymentInstallmentRead {
  id: string;
  sequence_number: number;
  due_date: string;
  amount_kopecks: number;
  salary_percent: number;
  employment_id: string;
  company_name: string;
  status: PaymentInstallmentStatus;
  paid_at: string | null;
  revoked_at: string | null;
  revocation_reason: string | null;
  payment_url: string | null;
  can_pay: boolean;
}

export interface PaymentSummaryRead {
  total_owed_kopecks: number;
  paid_kopecks: number;
  remaining_kopecks: number;
  overdue_kopecks: number;
  paid_installments: number;
  total_installments: number;
  paid_salary_percent: number;
  remaining_salary_percent: number;
}

export interface StudentPaymentDashboard {
  student_id: string;
  student_name: string;
  repayment_percent: number;
  mentor_reward_percent: number | null;
  employment: EmploymentRead | null;
  employment_history: EmploymentRead[];
  installments: PaymentInstallmentRead[];
  summary: PaymentSummaryRead;
  can_manage_employment: boolean;
  can_manage_payment_days: boolean;
}

export interface PaymentLinkRead {
  installment_id: string;
  payment_url: string;
  expires_in: number | null;
}

export interface AdminPaymentListItem {
  installment_id: string;
  student_id: string;
  student_name: string;
  student_telegram_username: string | null;
  mentor_id: string | null;
  mentor_name: string | null;
  company_name: string;
  due_date: string;
  amount_kopecks: number;
  status: PaymentInstallmentStatus;
  paid_at: string | null;
  mentor_reward_kopecks: number | null;
  mentor_reward_id: string | null;
  mentor_reward_paid_at: string | null;
  requires_manual_review: boolean;
}

export interface AdminPaymentStudentRead {
  student_id: string;
  student_name: string;
  student_telegram_username: string | null;
  mentor_id: string | null;
  mentor_name: string | null;
  company_name: string;
  employment_start_date: string;
  net_salary_kopecks: number;
  repayment_percent: number;
  total_owed_kopecks: number;
  paid_kopecks: number;
  remaining_kopecks: number;
  overdue_kopecks: number;
  overdue_payments: number;
  next_payment_date: string | null;
  paid_installments: number;
  total_installments: number;
}

export interface AdminPaymentStudentPage {
  items: AdminPaymentStudentRead[];
  total: number;
  limit: number;
  offset: number;
  total_remaining_kopecks: number;
  total_paid_kopecks: number;
  total_overdue_kopecks: number;
}

export interface AdminPaymentPage {
  items: AdminPaymentListItem[];
  total: number;
  limit: number;
  offset: number;
  scheduled_kopecks: number;
  paid_kopecks: number;
  overdue_kopecks: number;
  mentor_rewards_accrued_kopecks: number;
  mentor_rewards_paid_kopecks: number;
  mentor_rewards: MentorRewardRead[];
}

export interface MentorRewardRead {
  id: string;
  kind: MentorRewardKind;
  mentor_id: string;
  mentor_name: string;
  mentor_telegram_username: string | null;
  student_id: string;
  student_name: string;
  student_telegram_username: string | null;
  company_name: string | null;
  basis_kopecks: number | null;
  reward_percent: number | null;
  amount_kopecks: number;
  paid_kopecks: number;
  reserved_kopecks: number;
  available_kopecks: number;
  created_at: string;
  paid_at: string | null;
}

export interface MentorPayoutRead {
  id: string;
  mentor_id: string;
  mentor_name: string;
  mentor_telegram_username: string | null;
  amount_kopecks: number;
  origin: MentorPayoutOrigin;
  status: MentorPayoutStatus;
  payment_reference: string | null;
  created_at: string;
  paid_at: string | null;
  cancelled_at: string | null;
  cancellation_reason: string | null;
  edited_at: string | null;
  edit_reason: string | null;
  receipt_filename: string | null;
  receipt_content_type: string | null;
  receipt_size: number | null;
  receipt_uploaded_at: string | null;
}

export interface AdminMentorPayoutBalanceRead {
  mentor_id: string;
  mentor_name: string;
  mentor_telegram_username: string | null;
  accrued_kopecks: number;
  paid_kopecks: number;
  reserved_kopecks: number;
  available_kopecks: number;
}

export interface AdminMentorPayoutDashboard {
  balances: AdminMentorPayoutBalanceRead[];
  payouts: MentorPayoutRead[];
}

export interface AdminMentorPayoutDetail {
  mentor_id: string;
  mentor_name: string;
  mentor_telegram_username: string | null;
  accrued_kopecks: number;
  paid_kopecks: number;
  reserved_kopecks: number;
  available_kopecks: number;
  rewards: MentorRewardRead[];
  payouts: MentorPayoutRead[];
}

export interface MentorRewardSummary {
  mentor_id: string;
  accrued_kopecks: number;
  paid_kopecks: number;
  unpaid_kopecks: number;
  reserved_kopecks: number;
  available_kopecks: number;
  rewards: MentorRewardRead[];
  payouts: MentorPayoutRead[];
}

export interface MentorStudentRoadmapSummary {
  id: string;
  slug: string;
  title: string;
  completed_topics: number;
  total_topics: number;
  progress_percent: number;
  started_at: string | null;
  completed_at: string | null;
  overdue_sections: number;
}

export interface MentorCurrentTopic {
  id: string;
  title: string;
  section_title: string;
  roadmap_title: string;
  started_at: string;
  days_in_topic: number;
  deadline_at: string | null;
  is_overdue: boolean;
}

export interface MentorStudentListItem {
  id: string;
  first_name: string;
  last_name: string | null;
  email: string | null;
  telegram_username: string | null;
  is_active: boolean;
  learning_status: StudentLearningStatus;
  strength_level: StudentStrengthLevel | null;
  roadmaps: MentorStudentRoadmapSummary[];
  current_topics: MentorCurrentTopic[];
  last_progress_at: string | null;
  completed_topics_this_week: number;
  is_overdue: boolean;
  mock_interview_count: number;
}

export interface MentorStudentDirectionOption {
  id: string;
  slug: string;
  title: string;
}

export interface MentorStudentMentorOption {
  id: string;
  role: Schemas["UserRole"];
  first_name: string;
  last_name: string | null;
  telegram_username: string | null;
}

export interface MentorStudentPage {
  items: MentorStudentListItem[];
  total: number;
  limit: number;
  offset: number;
  directions: MentorStudentDirectionOption[];
  mentors: MentorStudentMentorOption[];
  can_filter_by_mentor: boolean;
}

export interface MentorNoteRead {
  id: string;
  body: string;
  author_name: string;
  is_own: boolean;
  created_at: string;
  updated_at: string;
}

export interface MentorDocumentRead {
  id: string;
  kind: MentorDocumentKind;
  text_content: string | null;
  file: InterviewAttachmentRead | null;
  created_at: string;
  updated_at: string;
}

export interface MockInterviewRead {
  id: string;
  mentor_name: string;
  student_id: string;
  scheduled_at: string;
  status: MockInterviewStatus;
  description: string | null;
  feedback: string | null;
  conducted_at: string | null;
  media: InterviewAttachmentRead | null;
  created_at: string;
  updated_at: string;
}

export interface MentorStudentDetail extends Omit<
  MentorStudentListItem,
  "roadmaps"
> {
  roadmaps: RoadmapDetail[];
  interviews: InterviewProcessSummary[];
  mock_interviews: MockInterviewRead[];
  documents: MentorDocumentRead[];
  notes: MentorNoteRead[];
}

export interface MentorInterviewDetail {
  process: InterviewProcessDetail;
  feedback: Array<{
    stage_id: string;
    comments: InterviewCatalogCommentRead[];
  }>;
}

export type IntelligenceInterviewType =
  | "hr"
  | "screening"
  | "technical"
  | "final"
  | "system_design"
  | "live_coding"
  | "other";
export type IntelligenceProcessingStatus =
  | "draft"
  | "uploaded"
  | "transcription_submitted"
  | "transcribing"
  | "transcript_ready"
  | "awaiting_candidate_speaker"
  | "analyzing"
  | "ready"
  | "failed";
export type IntelligenceSpeakerRole =
  "unknown" | "candidate" | "interviewer" | "recruiter" | "other";
export type IntelligenceReviewStatus =
  "suggested" | "approved" | "edited" | "rejected";
export type IntelligenceAssessment =
  | "correct"
  | "mostly_correct"
  | "partial"
  | "mostly_incorrect"
  | "incorrect"
  | "unable_to_assess";

export interface IntelligenceInterviewCreate {
  company_name: string;
  company_id?: string | null;
  company_alias?: string | null;
  company_alias_confirmed?: boolean;
  track_id: string;
  position_name?: string | null;
  interview_type: IntelligenceInterviewType;
  interviewed_at: string;
}

export interface IntelligenceInterviewSummary {
  id: string;
  stage_id: string;
  process_id: string;
  student_id: string;
  student_name: string;
  student_telegram_username: string | null;
  company_name: string;
  position_name: string | null;
  track_id: string;
  track_slug: string;
  track_title: string;
  interview_type: IntelligenceInterviewType;
  interviewed_at: string;
  processing_status: IntelligenceProcessingStatus;
  failed_stage: string | null;
  processing_error_code: string | null;
  processing_error_message: string | null;
  can_requeue_processing: boolean;
  duration_ms: number | null;
  question_count: number;
  suggested_review_count: number;
  reviewed_count: number;
  reviewed_at: string | null;
  reviewed_by_user_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface IntelligenceOperationsWorker {
  status: "healthy" | "unhealthy" | "unknown";
  heartbeat: string | null;
  heartbeat_ttl_seconds: number | null;
}

export interface AdminIntelligenceOperations {
  generated_at: string;
  total: number;
  by_status: Record<IntelligenceProcessingStatus, number>;
  active: number;
  failed: number;
  ready: number;
  oldest_active_at: string | null;
  oldest_active_age_seconds: number | null;
  launches_today: number;
  failure_codes_24h: Array<{ code: string; count: number }>;
  queues: {
    available: boolean;
    transcription_depth: number | null;
    openai_depth: number | null;
  };
  workers?: {
    transcription: IntelligenceOperationsWorker;
    openai: IntelligenceOperationsWorker;
  };
}

export interface IntelligenceInterviewPage {
  items: IntelligenceInterviewSummary[];
  total: number;
  limit: number;
  offset: number;
}

export interface AdminQuestionModerationSummary {
  question_id: string;
  interview_id: string;
  question_text: string;
  category: string;
  question_kind: "technical" | "hr" | "organizational" | "other";
  difficulty: "unknown" | "junior" | "middle" | "senior";
  moderation_status: "pending" | "mentor_approved" | "approved" | "rejected";
  company_name: string;
  track_id: string;
  track_slug: string;
  track_title: string;
  student_name: string;
  interviewed_at: string;
}

export interface AdminQuestionModerationDetail extends AdminQuestionModerationSummary {
  candidate_answer: string | null;
  suggested_answer: string | null;
  matched_card_id: string | null;
  matched_card_deck_id: string | null;
  matched_card_category: string | null;
  matched_card_question: string | null;
  matched_card_asked_count: number | null;
  card_candidates: AdminQuestionModerationCardCandidate[];
  deck_options: AdminQuestionModerationDeckOption[];
}

export interface AdminQuestionModerationCardCandidate {
  id: string;
  deck_id: string;
  deck_title: string;
  category: string;
  question_markdown: string;
  matched_text: string;
  asked_count: number;
  frequency: "frequent" | "occasional";
  similarity: number;
  match_type: "exact" | "similar";
  matched_source: "card" | "approved_alias";
}

export interface AdminQuestionModerationDeckOption {
  id: string;
  title: string;
  categories: string[];
}

export interface AdminQuestionModerationPage {
  items: AdminQuestionModerationSummary[];
  total: number;
  limit: number;
  offset: number;
}

export interface IntelligenceUtterance {
  id: string;
  speaker_id: string;
  speaker_key: string;
  speaker_role: IntelligenceSpeakerRole;
  sequence_number: number;
  start_ms: number;
  end_ms: number;
  text: string;
}

export interface IntelligenceSpeaker {
  id: string;
  provider_speaker_key: string;
  role: IntelligenceSpeakerRole;
  display_name: string | null;
  examples: IntelligenceUtterance[];
}

export interface IntelligenceReview {
  id: string;
  parent_review_id: string | null;
  source: "ai" | "mentor";
  status: IntelligenceReviewStatus;
  assessment: IntelligenceAssessment;
  score: number | null;
  summary: string | null;
  strengths: Array<Record<string, unknown>>;
  problems: Array<Record<string, unknown>>;
  missing_points: unknown[];
  incorrect_statements: Array<Record<string, unknown>>;
  suggested_better_answer: string | null;
  model_name: string | null;
  prompt_version: string | null;
  created_by_user_id: string | null;
  rejection_reason: string | null;
  created_at: string;
}

export interface IntelligenceQuestion {
  id: string;
  sequence_number: number;
  question_text: string;
  question_start_ms: number;
  question_end_ms: number | null;
  answer_start_ms: number | null;
  answer_end_ms: number | null;
  category: string;
  question_kind: "technical" | "hr" | "organizational" | "other";
  subcategory: string | null;
  difficulty: "unknown" | "junior" | "middle" | "senior";
  confidence: number;
  is_low_confidence: boolean;
  moderation_status: "pending" | "mentor_approved" | "approved" | "rejected";
  published_card_id: string | null;
  answer: {
    id: string;
    answer_text: string;
    start_ms: number | null;
    end_ms: number | null;
    reviews: IntelligenceReview[];
  } | null;
}

export interface IntelligenceMentorComment {
  id: string;
  mentor_id: string;
  mentor_name: string;
  mentor_telegram_username: string | null;
  question_id: string | null;
  timestamp_ms: number | null;
  text: string;
  created_at: string;
  updated_at: string;
}

export interface IntelligenceProcessing {
  status: IntelligenceProcessingStatus;
  failed_stage: string | null;
  error_code: string | null;
  error_message: string | null;
  transcribed: boolean;
  candidate_selected: boolean;
  questions_found: number;
  reviews_completed: number;
  attempts: Array<{
    id: string;
    stage: string;
    status: "started" | "completed" | "failed";
    attempt_number: number;
    provider: string | null;
    error_code: string | null;
    error_message: string | null;
    started_at: string;
    finished_at: string | null;
  }>;
}

export interface IntelligenceCommunicationDimension {
  name: string;
  score: number | null;
  summary: string;
  evidence_utterance_ids: string[];
  confidence: number;
}

export interface IntelligenceInterviewOverview {
  overall_summary: string;
  key_topics: string[];
  communication_summary: string;
  communication_score: number | null;
  communication_dimensions: IntelligenceCommunicationDimension[];
  communication_strengths: string[];
  communication_growth_areas: string[];
  caveats: string[];
  model_name: string | null;
  prompt_version: string | null;
}

export interface IntelligenceInterviewDetail extends IntelligenceInterviewSummary {
  media_filename: string | null;
  media_content_type: string | null;
  media_size: number | null;
  speakers: IntelligenceSpeaker[];
  transcript: IntelligenceUtterance[];
  questions: IntelligenceQuestion[];
  mentor_comments: IntelligenceMentorComment[];
  overview: IntelligenceInterviewOverview | null;
  processing: IntelligenceProcessing;
}
