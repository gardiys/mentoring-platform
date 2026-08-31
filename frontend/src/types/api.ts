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
  public_identity_hidden_at: string | null;
  public_identity_hidden_reason: string | null;
  personal_data_erased_at: string | null;
  personal_data_erasure_reason: string | null;
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
  public_identity_hidden_at: string | null;
  public_identity_hidden_reason: string | null;
  personal_data_erased_at: string | null;
  personal_data_erasure_reason: string | null;
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
export type InterviewQuestionLearnedFilter = "all" | "learned" | "unlearned";
export interface InterviewQuestionTableItem {
  id: string;
  slug: string;
  category: string;
  subcategory: string | null;
  question_markdown: string;
  answer_markdown: string;
  frequency: "frequent" | "occasional";
  learned: boolean;
  learned_at: string | null;
  repetitions: number;
  due_at: string | null;
}
export interface InterviewQuestionTablePage {
  deck: InterviewDeckListItem;
  items: InterviewQuestionTableItem[];
  total: number;
  limit: number;
  offset: number;
}
export interface InterviewQuestionLearnedResult {
  card_id: string;
  learned: boolean;
  learned_at: string | null;
  due_at: string | null;
}
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

export type RecruiterFeedbackKind = Schemas["RecruiterFeedbackKind"];
export type RecruiterFeedbackRead = Schemas["RecruiterFeedbackRead"];
export type RecruiterContactRead = Schemas["RecruiterContactRead"];
export type RecruiterContactPage = Schemas["RecruiterContactPage"];
export type RecruiterContactOpenRead = Schemas["RecruiterContactOpenRead"];
export type RecruiterFeedbackMutation = Schemas["RecruiterFeedbackMutation"];
export type RecruiterSort = Schemas["RecruiterSort"];

export interface InterviewCatalogFilters {
  query: string;
  authorId: string | null;
  trackId: string | null;
  stageType: InterviewStageType | null;
  hasOffer: boolean;
  mediaKind: InterviewCatalogMediaKind | null;
  hasAiReview: boolean;
  favoritesOnly: boolean;
  recruiterUsername: string;
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

export interface MentorTrackCalendarMutation {
  track_id: string;
  calendar_url: string;
}

export interface MentorTrackCalendarRead {
  track: ScheduleTrackRead;
  calendar_url: string;
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
  group_calendars: MentorTrackCalendarRead[];
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
  group_calendars: MentorTrackCalendarRead[];
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
export type PaymentAttemptStatus =
  "pending" | "approved" | "failed" | "cancelled" | "manual_review" | "revoked";
export type AdminEmploymentPaymentStatus = "outstanding" | "paid" | "all";
export type StudentEmploymentStatus = "active" | "terminated";
export type MentorRewardKind =
  | "employment_payment"
  | "entry_payment"
  | "program_exclusion"
  | "legacy_fixed"
  | "consultation";
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
  due_date_changed_at?: string | null;
  previous_due_date?: string | null;
  due_date_change_reason?: string | null;
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

export interface AdminTochkaTestPaymentRead {
  id: string;
  amount_kopecks: number;
  status: PaymentAttemptStatus;
  payment_url: string | null;
  provider_operation_id: string | null;
  approved_at: string | null;
  created_at: string;
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
  employment_id: string;
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

export type MentorStudentActivityKind =
  "roadmap" | "interview" | "interview_cards";
export type MentorStudentAttentionReason =
  "roadmap_overdue" | "interviews_not_published";

export type MentorStudentSort =
  | "name_asc"
  | "learning_start_desc"
  | "learning_start_asc"
  | "last_activity_desc"
  | "last_activity_asc";

export interface MentorStudentListItem {
  id: string;
  first_name: string;
  last_name: string | null;
  email: string | null;
  telegram_username: string | null;
  learning_start_date: string | null;
  is_active: boolean;
  learning_status: StudentLearningStatus;
  strength_level: StudentStrengthLevel | null;
  roadmaps: MentorStudentRoadmapSummary[];
  current_topics: MentorCurrentTopic[];
  last_progress_at: string | null;
  last_activity_kind: MentorStudentActivityKind | null;
  completed_topics_this_week: number;
  is_overdue: boolean;
  attention_reason: MentorStudentAttentionReason | null;
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

export type MentorAnalyticsPeriod = "week" | "month" | "all";

export interface MentorInterviewStageCount {
  stage_type: InterviewStageType;
  count: number;
}

export interface MentorInterviewRankingItem {
  position: number;
  student_id: string;
  first_name: string;
  last_name: string | null;
  telegram_username: string | null;
  interview_count: number;
  company_count: number;
  offer_count: number;
  ai_analysis_count: number;
  last_interview_at: string | null;
}

export interface MentorInterviewAnalytics {
  period: MentorAnalyticsPeriod;
  period_start: string | null;
  period_end: string;
  selected_student_count: number;
  current_interviewing_students: number;
  students_with_interviews: number;
  students_without_interviews: number;
  total_interviews: number;
  unique_companies: number;
  active_processes: number;
  offers_received: number;
  ai_analyses_started: number;
  ai_analyses_ready: number;
  ai_analyses_failed: number;
  interviews_with_recording: number;
  upcoming_interviews_next_week: number;
  average_interviews_per_participant: number;
  offer_conversion_percent: number;
  ai_success_rate_percent: number;
  recording_coverage_percent: number;
  stage_counts: MentorInterviewStageCount[];
  ranking: MentorInterviewRankingItem[];
}

export interface MentorEfficiencyItem {
  mentor_id: string;
  role: Schemas["UserRole"];
  first_name: string;
  last_name: string | null;
  telegram_username: string | null;
  assigned_students: number;
  interviewing_students: number;
  active_interviewing_students: number;
  recording_students: number;
  inactive_interviewing_students: number;
  interview_count: number;
  recording_count: number;
  ai_analysis_count: number;
  offer_count: number;
  upcoming_students: number;
  participation_percent: number;
  recording_participation_percent: number;
  average_interviews_per_active_student: number;
  last_interview_at: string | null;
}

export interface MentorEfficiencyAnalytics {
  period: MentorAnalyticsPeriod;
  period_start: string | null;
  period_end: string;
  mentor_count: number;
  assigned_students: number;
  interviewing_students: number;
  active_interviewing_students: number;
  inactive_interviewing_students: number;
  unassigned_students: number;
  unassigned_interviewing_students: number;
  mentors: MentorEfficiencyItem[];
}

export interface MentorStudentStatusPeriod {
  status: StudentLearningStatus;
  started_at: string;
  ended_at: string | null;
  days: number;
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
  status_history: MentorStudentStatusPeriod[];
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
  matched_card_answer: string | null;
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
  answer_markdown: string;
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

export type LearningObjectType =
  | "flashcard"
  | "open_technical_question"
  | "coding_task"
  | "system_design_case"
  | "behavioral_question"
  | "organizational_question"
  | "context_dependent"
  | "noise";

export type QuestionClusterStatus =
  | "shadow"
  | "candidate"
  | "needs_review"
  | "linked"
  | "card_created"
  | "deferred"
  | "ignored"
  | "split"
  | "merged";

export type QuestionOccurrenceStatus =
  | "created"
  | "routing"
  | "routed"
  | "auto_ignored"
  | "searching_card"
  | "auto_linked"
  | "searching_cluster"
  | "clustered"
  | "needs_review"
  | "personal_only"
  | "failed";

export type AnswerContractStatus =
  | "generated_from_sources"
  | "needs_expert_source"
  | "needs_manual_review"
  | "approved"
  | "rejected";

export type AutomationDecisionType =
  | "question_routed"
  | "routed_as_noise"
  | "routed_as_non_flashcard"
  | "exact_card_match"
  | "alias_card_match"
  | "semantic_card_match"
  | "cluster_match"
  | "shadow_cluster_created"
  | "cluster_promoted"
  | "personal_review_created"
  | "personal_review_reviewed"
  | "personal_review_archived"
  | "answer_contract_generated"
  | "answer_contract_validated"
  | "answer_contract_needs_source"
  | "answer_contract_failed"
  | "answer_validation_failed"
  | "manual_override"
  | "cluster_linked"
  | "card_created"
  | "cluster_split"
  | "cluster_merged"
  | "cluster_ignored"
  | "cluster_deferred"
  | "cluster_reopened"
  | "cluster_marked_important"
  | "occurrence_failed"
  | "occurrence_reprocessed";

export type AutomationDecisionSource =
  | "rule"
  | "ai_routing"
  | "exact"
  | "confirmed_alias"
  | "semantic_judge"
  | "clustering"
  | "human"
  | "backfill";

export type AutomationReviewResult =
  | "correct"
  | "merge_error"
  | "classification_error"
  | "wrong_object_type"
  | "wrong_topic"
  | "other";

export type PairwiseCardMatchDecision =
  "same_card" | "related_different_scope" | "not_related" | "uncertain";

export type QuestionClusterAction =
  | "link_card"
  | "create_card"
  | "update_draft"
  | "split"
  | "merge"
  | "ignore"
  | "defer"
  | "mark_important"
  | "reopen";

export interface CardAutomationAnswerContract {
  short_answer: string;
  required_points: string[];
  optional_points: string[];
  common_mistakes: string[];
  unsupported_claims: string[];
  follow_up_questions: string[];
  difficulty: "junior" | "middle" | "senior" | "mixed";
  version_scope: string[];
  source_references: string[];
  confidence: number;
}

export interface CardAutomationAnswerValidation {
  supported: boolean;
  unsupported_claims: string[];
  contradictions: string[];
  missing_required_points: string[];
  version_sensitive_claims: string[];
  confidence: number;
}

export interface CardAutomationCardCandidate {
  card_id: string;
  question_markdown: string;
  answer_markdown: string;
  category: string;
  semantic_score: number;
  combined_score: number | null;
  judge_decision: PairwiseCardMatchDecision | null;
  judge_confidence: number | null;
  judge_reason: string | null;
  is_confirmed_alias: boolean;
}

export interface QuestionClusterSummary {
  id: string;
  direction_id: string;
  direction_title: string;
  direction_slug: string;
  status: QuestionClusterStatus;
  canonical_question: string;
  learning_object_type: LearningObjectType;
  deck_id: string | null;
  topic_name: string | null;
  subtopic_name: string | null;
  topic_candidates: string[];
  linked_card_id: string | null;
  last_decision_source: AutomationDecisionSource | null;
  occurrences_count: number;
  distinct_interviews_count: number;
  distinct_companies_count: number;
  distinct_students_count: number;
  failed_answers_count: number;
  priority_score: number;
  quality_score: number;
  cluster_confidence: number;
  best_match: CardAutomationCardCandidate | null;
  first_seen_at: string;
  last_seen_at: string;
  manual_important: boolean;
  version: number;
  allowed_actions: QuestionClusterAction[];
}

export interface QuestionClusterTopicOption {
  deck_id: string;
  deck_title: string;
  topics: string[];
}

export interface QuestionClusterOccurrence {
  id: string;
  interview_id: string;
  student_id: string;
  student_name: string;
  company_id: string | null;
  company_name: string;
  interviewed_at: string;
  question_text: string;
  canonical_question_candidate: string | null;
  source_context: string | null;
  answer_text: string | null;
  answer_assessment: string | null;
  learning_object_type: LearningObjectType;
  routing_confidence: number | null;
  quality_flags: string[];
  automation_status: QuestionOccurrenceStatus;
  automation_revision: number;
  automation_error: string | null;
  created_at: string;
}

export interface QuestionOccurrenceReprocessMutation {
  expected_revision: number;
  reason: string;
}

export interface QuestionOccurrenceReprocessResult {
  question_id: string;
  revision: number;
  job_id: string;
}

export interface QuestionClusterAnswerGenerationMutation {
  expected_version: number;
}

export interface QuestionClusterAnswerGenerationResult {
  cluster_id: string;
  version: number;
  job_id: string;
}

export interface QuestionClusterDetail extends QuestionClusterSummary {
  normalized_canonical_question: string;
  representative_occurrence_id: string | null;
  merged_into_cluster_id: string | null;
  parent_cluster_id: string | null;
  question_variants: Array<{
    question_text: string;
    normalized_question_text: string;
    occurrences_count: number;
    first_seen_at: string;
    last_seen_at: string;
  }>;
  companies: Array<{
    company_id: string | null;
    company_name: string;
    occurrences_count: number;
  }>;
  interviews: Array<{
    interview_id: string;
    company_id: string | null;
    company_name: string;
    interviewed_at: string;
    occurrences_count: number;
  }>;
  answer_contract: CardAutomationAnswerContract | null;
  answer_validation: CardAutomationAnswerValidation | null;
  answer_status: AnswerContractStatus | null;
  occurrences: QuestionClusterOccurrence[];
  top_card_matches: CardAutomationCardCandidate[];
  decisions: AutomationDecisionRead[];
  topic_options: QuestionClusterTopicOption[];
  manual_history: Array<{
    id: string;
    action: string;
    actor_user_id: string | null;
    actor_name: string | null;
    reason: string | null;
    changes: Record<string, unknown>;
    created_at: string;
  }>;
  promoted_at: string | null;
  promotion_reason: string | null;
  membership_revision: number;
  stats_revision: number;
}

export interface QuestionClusterPage {
  items: QuestionClusterSummary[];
  total: number;
  limit: number;
  offset: number;
}

export interface InterviewCardDuplicateCard {
  id: string;
  deck_id: string;
  deck_title: string;
  direction_id: string;
  direction_slug: string;
  direction_title: string;
  category: string;
  subcategory: string | null;
  question_markdown: string;
  answer_markdown: string;
  companies: string | null;
  asked_count: number;
  frequency: "frequent" | "occasional";
  updated_at: string;
}

export interface InterviewCardDuplicateCandidate {
  pair_key: string;
  similarity: number;
  matched_source: string;
  matched_text: string;
  left: InterviewCardDuplicateCard;
  right: InterviewCardDuplicateCard;
}

export interface InterviewCardDuplicatePage {
  items: InterviewCardDuplicateCandidate[];
  total: number;
  limit: number;
  offset: number;
  cache_status: "ready" | "building";
  cache_generated_at: string | null;
  cache_refreshing: boolean;
}

export interface InterviewCardDuplicateRefreshRead {
  status: "queued" | "already_running";
}

export interface InterviewCardDuplicateMutation {
  left_card_id: string;
  right_card_id: string;
  expected_left_updated_at: string;
  expected_right_updated_at: string;
  reason: string;
}

export interface InterviewCardDuplicateMergeMutation extends InterviewCardDuplicateMutation {
  primary_card_id: string;
}

export interface InterviewCardDuplicateReviewResult {
  review_id: string;
  decision: "merged" | "not_duplicate";
  primary_card_id: string | null;
  archived_card_id: string | null;
  moved_occurrences: number;
  deduplicated_occurrences: number;
  merged_progress_records: number;
}

export interface QuestionClusterFilters {
  directionId: string | null;
  statuses: QuestionClusterStatus[];
  topicName: string | null;
  learningObjectTypes: LearningObjectType[];
  minDistinctInterviews: number | null;
  minDistinctCompanies: number | null;
  hasFailedAnswers: boolean | null;
  minConfidence: number | null;
  maxConfidence: number | null;
  hasPossibleDuplicate: boolean | null;
  decisionSource: AutomationDecisionSource | null;
  seenFrom: string | null;
  seenTo: string | null;
  needsActionOnly: boolean;
  sortBy:
    | "priority_score"
    | "last_seen_at"
    | "first_seen_at"
    | "occurrences_count"
    | "cluster_confidence";
  sortOrder: "asc" | "desc";
}

export interface AutomationDecisionRead {
  id: string;
  entity_type: string;
  entity_id: string;
  entity_version: number | null;
  question_text: string | null;
  decision_type: AutomationDecisionType;
  decision_source: AutomationDecisionSource;
  selected_card_id: string | null;
  selected_card_question: string | null;
  selected_cluster_id: string | null;
  selected_cluster_question: string | null;
  candidate_card_ids: string[];
  candidate_cluster_ids: string[];
  retrieval_scores: Record<string, unknown>;
  judge_result: Record<string, unknown> | null;
  confidence: number | null;
  similarity_score: number | null;
  reason: string;
  model_provider: string | null;
  model_name: string | null;
  prompt_version: string | null;
  schema_version: string | null;
  input_tokens: number | null;
  output_tokens: number | null;
  cost: string | null;
  latency_ms: number | null;
  is_audit_sample: boolean;
  review_result: AutomationReviewResult | null;
  reviewed_by_user_id: string | null;
  reviewed_by_name: string | null;
  reviewed_at: string | null;
  review_reason: string | null;
  is_overridden: boolean;
  overridden_by_user_id: string | null;
  overridden_by_name: string | null;
  override_reason: string | null;
  overridden_at: string | null;
  created_at: string;
}

export interface AutomationDecisionPage {
  items: AutomationDecisionRead[];
  total: number;
  limit: number;
  offset: number;
}

export interface AutomationDecisionFilters {
  directionId: string | null;
  entityType: string | null;
  decisionTypes: AutomationDecisionType[];
  decisionSources: AutomationDecisionSource[];
  isAuditSample: boolean | null;
  isReviewed: boolean | null;
  isOverridden: boolean | null;
  createdFrom: string | null;
  createdTo: string | null;
  sortOrder: "asc" | "desc";
}

export interface AutomationDecisionReviewMutation {
  result: AutomationReviewResult;
  reason: string | null;
}

export interface AutomationDecisionOverrideMutation {
  expected_entity_version: number;
  replacement_decision_type: AutomationDecisionType;
  selected_card_id: string | null;
  selected_cluster_id: string | null;
  reason: string;
}

export interface CardAutomationSettingsRead {
  direction_id: string;
  direction_title: string;
  direction_slug: string;
  enabled: boolean;
  shadow_mode: boolean;
  auto_ignore_noise_enabled: boolean;
  auto_link_exact_enabled: boolean;
  auto_link_alias_enabled: boolean;
  auto_link_semantic_enabled: boolean;
  semantic_similarity_threshold: number;
  pairwise_judge_confidence_threshold: number;
  candidate_score_gap_threshold: number;
  cluster_match_threshold: number;
  min_distinct_interviews_for_promotion: number;
  min_distinct_companies_for_promotion: number;
  min_failed_answers_for_promotion: number;
  audit_sample_percent: number;
  personal_review_enabled: boolean;
  global_auto_publish_enabled: boolean;
  cluster_moderation_enabled: boolean;
  legacy_queue_enabled: boolean;
  version: number;
  updated_at: string;
}

export interface CardAutomationSettingsPage {
  items: CardAutomationSettingsRead[];
}

export type CardAutomationSettingsMutation = Omit<
  CardAutomationSettingsRead,
  | "direction_title"
  | "direction_slug"
  | "updated_at"
  | "version"
  | "global_auto_publish_enabled"
> & { expected_version: number; global_auto_publish_enabled: false };

export interface QuestionClusterVersionMutation {
  expected_version: number;
  reason: string;
}

export interface QuestionClusterLinkCardMutation extends QuestionClusterVersionMutation {
  card_id: string;
  confirm_alias: boolean;
}

export interface QuestionClusterCreateCardMutation extends QuestionClusterVersionMutation {
  deck_id: string;
  category: string;
  subcategory?: string | null;
  question_markdown: string;
  answer_markdown: string;
  frequency: "frequent" | "occasional";
  frequency_mode: "automatic" | "manual";
}

export interface QuestionClusterDraftMutation extends QuestionClusterVersionMutation {
  canonical_question?: string;
  topic_name?: string | null;
  subtopic_name?: string | null;
  answer_contract?: CardAutomationAnswerContract;
  preserve_answer_status?: boolean;
}

export interface QuestionClusterSplitMutation extends QuestionClusterVersionMutation {
  occurrence_ids: string[];
  new_canonical_question: string;
  new_topic_name?: string | null;
  new_subtopic_name?: string | null;
}

export interface QuestionClusterMergeMutation extends QuestionClusterVersionMutation {
  target_cluster_id: string;
  target_expected_version: number;
}

export interface QuestionClusterActionResult {
  cluster: QuestionClusterSummary;
  decision_id: string;
  created_card_id?: string | null;
  affected_cluster_ids: string[];
}

export type QuestionClusterBulkAction =
  | "confirm_exact_matches"
  | "confirm_high_confidence_matches"
  | "ignore_noise"
  | "defer_singletons"
  | "link_card"
  | "apply_topic";

export interface QuestionClusterBulkMutation {
  action: QuestionClusterBulkAction;
  cluster_ids: string[];
  expected_versions: Record<string, number>;
  confirmation: true;
  reason: string;
  card_id: string | null;
  topic_name: string | null;
}

export interface QuestionClusterBulkItemResult {
  cluster_id: string;
  succeeded: boolean;
  cluster: QuestionClusterSummary | null;
  decision_id: string | null;
  error_code: string | null;
  error_message: string | null;
}

export interface QuestionClusterBulkResult {
  requested_count: number;
  succeeded_count: number;
  failed_count: number;
  items: QuestionClusterBulkItemResult[];
}

export interface CardAutomationMetricsFilters {
  periodFrom: string;
  periodTo: string;
  directionId: string | null;
}

export interface CardAutomationMetricsRead {
  period_from: string;
  period_to: string;
  direction_id: string | null;
  direction_slug: string | null;
  extracted_questions_total: number;
  routed_as_noise_total: number;
  routed_as_non_flashcard_total: number;
  auto_linked_exact_total: number;
  auto_linked_alias_total: number;
  auto_linked_semantic_total: number;
  shadow_clusters_created_total: number;
  clusters_promoted_total: number;
  clusters_reviewed_total: number;
  personal_review_items_created_total: number;
  manual_tasks_per_100_interviews: number;
  average_cluster_moderation_time: number;
  oldest_moderation_task_age: number;
  automatic_decision_override_rate: number;
  false_merge_rate: number;
  noise_false_positive_rate: number;
  average_ai_cost_per_interview: string;
  average_ai_cost_per_question: string;
  average_ai_cost_per_promoted_cluster: string;
  generated_at: string;
}

export type PersonalReviewStatus =
  "active" | "mastered" | "archived" | "replaced_by_canonical_card";

export interface PersonalReviewItemRead {
  id: string;
  direction_id: string;
  direction_title: string;
  direction_slug: string;
  source_occurrence_id: string | null;
  source_analysis_id: string | null;
  source_analysis_url: string | null;
  canonical_card_id: string | null;
  question_text: string;
  answer_summary: string | null;
  answer_contract: CardAutomationAnswerContract | null;
  status: PersonalReviewStatus;
  due_at: string;
  last_reviewed_at: string | null;
  successful_reviews_count: number;
  expires_at: string | null;
  replaced_by_card_id: string | null;
  version: number;
  created_at: string;
  updated_at: string;
}

export interface PersonalReviewItemPage {
  items: PersonalReviewItemRead[];
  total: number;
  limit: number;
  offset: number;
}

export interface PersonalReviewFilters {
  directionId: string | null;
  statuses: PersonalReviewStatus[];
  dueOnly: boolean;
  dueBefore: string | null;
  sortOrder: "asc" | "desc";
}

export interface PersonalReviewMutation {
  rating: InterviewReviewRating;
  expected_version: number;
}

export interface PersonalReviewResult {
  item: PersonalReviewItemRead;
  rating: InterviewReviewRating;
  became_mastered: boolean;
}

export interface ManagedPersonalReviewMutation {
  expected_version: number;
  reason: string;
  question_text?: string | null;
  answer_summary?: string | null;
  answer_contract?: CardAutomationAnswerContract | null;
  due_at?: string | null;
  status?: PersonalReviewStatus | null;
}

export interface ManagedPersonalReviewResult {
  item: PersonalReviewItemRead;
  decision_id: string;
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

export type NotificationKind =
  | "interview_published"
  | "mock_interview"
  | "mock_feedback"
  | "mentor_document"
  | "offer"
  | "status_changed"
  | "mentor_feedback"
  | "payment_due";

export interface PlatformNotification {
  id: string;
  kind: NotificationKind;
  title: string;
  body: string;
  action_url: string;
  read_at: string | null;
  created_at: string;
}

export interface NotificationPage {
  items: PlatformNotification[];
  total: number;
  unread_count: number;
  limit: number;
  offset: number;
}

export type OnboardingApplicationAction =
  | "approve_qualification"
  | "reject_qualification"
  | "approve_after_call"
  | "reject_after_call"
  | "request_follow_up"
  | "confirm_payment"
  | "resend_payment"
  | "complete_onboarding"
  | "confirm_access"
  | "access_missing"
  | "mark_contact_lost"
  | "defer_candidate"
  | "rollback_status";

export interface OnboardingApplicationListItem {
  applicant_id: string;
  status: string;
  name: string | null;
  telegram_user_id: number;
  telegram_username: string | null;
  email: string | null;
  direction: string | null;
  city: string | null;
  admin_comment: string | null;
  booking_start_time: string | null;
  payment_status: string | null;
  created_at: string;
  updated_at: string;
  available_actions: OnboardingApplicationAction[];
}

export interface OnboardingApplicationPage {
  items: OnboardingApplicationListItem[];
  total: number;
  limit: number;
  offset: number;
  status_counts: Record<string, number>;
}

export interface OnboardingApplicationEvent {
  event_type: string;
  old_status: string | null;
  new_status: string | null;
  source: string;
  payload: Record<string, unknown> | null;
  created_at: string;
}

export interface OnboardingApplicationBooking {
  status: string;
  start_time: string | null;
  end_time: string | null;
  meeting_url: string | null;
  created_at: string;
}

export interface OnboardingApplicationPayment {
  status: string;
  amount: string;
  currency: string;
  payment_url: string | null;
  approved_at: string | null;
  created_at: string;
}

export interface OnboardingApplicationFormDocument {
  uploaded: boolean;
  url: string | null;
  content_type: string | null;
  size: number | null;
}

export interface OnboardingApplicationDetail extends OnboardingApplicationListItem {
  rollback_status: string | null;
  age: string | null;
  initial_knowledge: string | null;
  life_difficulties: string | null;
  study_time_per_day: string | null;
  military_document_status: string | null;
  referral_source: string | null;
  form_answers: Record<string, unknown>;
  form_answer_source: "database" | "redis_draft" | "none";
  form_state: string | null;
  form_complete: boolean;
  form_missing_fields: string[];
  form_documents: Record<string, OnboardingApplicationFormDocument>;
  bookings: OnboardingApplicationBooking[];
  payments: OnboardingApplicationPayment[];
  events: OnboardingApplicationEvent[];
}

export interface OnboardingApplicationActionResponse {
  message: string;
  delivered: boolean | null;
  application: OnboardingApplicationDetail;
}

export type OpportunitySegment =
  "ACTIVE_STUDENT" | "PYTHON_ALUMNI" | "GO_ALUMNI" | "MULTI_ALUMNI" | "OTHER";
export type ConsultationStatus =
  | "requested"
  | "payment_pending"
  | "paid"
  | "scheduled"
  | "completed"
  | "cancelled";
export type ConsultationType =
  | "free_topic"
  | "technical_mock"
  | "legend_mock"
  | "resume_legend"
  | "system_design_mock"
  | "work_task";
export type GoTransitionStatus =
  | "submitted"
  | "approved"
  | "payment_pending"
  | "paid"
  | "rejected"
  | "cancelled";
export interface OpportunityMentor {
  id: string;
  first_name: string;
  last_name: string | null;
  telegram_username: string | null;
}
export interface OpportunityOffer {
  code:
    "ALUMNI_CONSULTATION" | "PYTHON_REPEAT_MENTORSHIP" | "PYTHON_TO_GO_ALUMNI";
  available: boolean;
  title: string;
  unavailable_reason: string | null;
  price: { amount_kopecks: number; currency: string } | null;
  comparison_price: { amount_kopecks: number; currency: string } | null;
  upfront_price_kopecks: number | null;
  success_fee_percent: number | null;
  comparison_upfront_price_kopecks: number | null;
  comparison_success_fee_percent: number | null;
}
export interface ConsultationRequestRead {
  id: string;
  mentor: OpportunityMentor | null;
  consultation_type: ConsultationType;
  brief: string;
  price_kopecks: number;
  duration_minutes: number;
  status: ConsultationStatus;
  scheduled_at: string | null;
  paid_at: string | null;
  completed_at: string | null;
  admin_note: string | null;
  written_summary: string | null;
  created_at: string;
}
export interface GoTransitionApplicationRead {
  id: string;
  motivation: string;
  status: GoTransitionStatus;
  upfront_price_kopecks: number;
  success_fee_percent: number;
  approved_at: string | null;
  terms_accepted_at: string | null;
  paid_at: string | null;
  admin_note: string | null;
  terms_version: number;
  terms_snapshot: Record<string, unknown>;
  terms_expires_at: string | null;
  accepted_terms_snapshot: Record<string, unknown> | null;
  created_at: string;
}
export interface OpportunitiesDashboard {
  opportunities_enabled: boolean;
  consultations_enabled: boolean;
  python_repeat_mentorship_enabled: boolean;
  python_to_go_enabled: boolean;
  segment: OpportunitySegment;
  has_active_program: boolean;
  has_alumni_access: boolean;
  opportunities: OpportunityOffer[];
  mentors: OpportunityMentor[];
  consultation_types: Array<{
    code: ConsultationType;
    title: string;
    description: string;
    price_kopecks: number;
    comparison_price_kopecks: number;
    mentor_reward_kopecks: number;
    duration_minutes: number;
  }>;
  go_transition_description_markdown: string;
  consultations: ConsultationRequestRead[];
  go_transition_applications: GoTransitionApplicationRead[];
}
export interface AdminOpportunityStudent {
  id: string;
  first_name: string;
  last_name: string | null;
  telegram_username: string | null;
  email: string | null;
}
export interface AdminConsultationRead extends ConsultationRequestRead {
  student: AdminOpportunityStudent;
  mentor_reward_kopecks: number;
}
export interface AdminConsultationMentor extends OpportunityMentor {
  is_enabled: boolean;
}
export interface AdminGoTransitionRead extends GoTransitionApplicationRead {
  student: AdminOpportunityStudent;
}
export interface AdminOpportunitiesDashboard {
  consultation_types: OpportunitiesDashboard["consultation_types"];
  go_transition_description_markdown: string;
  consultation_mentors: AdminConsultationMentor[];
  consultations: AdminConsultationRead[];
  go_transition_applications: AdminGoTransitionRead[];
}
export interface OpportunityPaymentLink {
  payment_url: string;
  payment_link_id: string;
}

export type PythonRepeatApplicationStatus =
  | "draft"
  | "submitted"
  | "under_review"
  | "needs_diagnostic"
  | "needs_clarification"
  | "approved"
  | "rejected"
  | "terms_accepted"
  | "payment_pending"
  | "paid"
  | "enrolled"
  | "cancelled"
  | "expired";

export interface PythonRepeatApplication {
  id: string;
  student_id: string;
  employment_status: string;
  reason: string;
  current_position: string | null;
  current_company: string | null;
  current_stack: string | null;
  last_interview_at: string | null;
  target_position: string;
  target_salary_kopecks: number | null;
  technical_gaps: string;
  hours_per_week: number;
  desired_start_date: string | null;
  search_mode: string;
  additional_comment: string | null;
  status: PythonRepeatApplicationStatus;
  responsible_user_id: string | null;
  eligibility_override_reason: string | null;
  admin_comment: string | null;
  terms_version: number | null;
  terms_snapshot: Record<string, unknown> | null;
  approved_at: string | null;
  offer_expires_at: string | null;
  accepted_at: string | null;
  paid_at: string | null;
  created_at: string;
  history: Array<{
    old_status: PythonRepeatApplicationStatus | null;
    new_status: PythonRepeatApplicationStatus;
    actor_user_id: string | null;
    comment: string | null;
    created_at: string;
  }>;
}

export interface PythonRepeatEnrollment {
  id: string;
  application_id: string;
  student_id: string;
  track_id: string;
  previous_track_id: string;
  mentor_id: string | null;
  mentor_assigned_at: string | null;
  status: "active" | "completed" | "cancelled";
  started_at: string;
  ended_at: string | null;
  personal_plan_markdown: string | null;
  terms_snapshot: Record<string, unknown>;
}

export interface PythonRepeatEmploymentOffer {
  id: string;
  enrollment_id: string;
  student_id: string;
  position: string;
  company: string;
  technology_direction: string;
  fixed_monthly_salary_kopecks: number;
  currency: string;
  employment_type: string | null;
  received_at: string;
  expected_start_date: string;
  status:
    | "draft"
    | "submitted"
    | "under_review"
    | "verified"
    | "rejected"
    | "cancelled";
  submitted_at: string | null;
  verified_at: string | null;
  verification_comment: string | null;
  created_at: string;
}

export interface PythonRepeatInstallment {
  id: string;
  sequence_number: number;
  amount_kopecks: number;
  salary_percent: number;
  due_at: string;
  status: "scheduled" | "pending" | "paid" | "refunded" | "cancelled";
  paid_at: string | null;
  actual_received_kopecks: number | null;
  refunded_at: string | null;
}

export interface PythonRepeatDashboard {
  enabled: boolean;
  eligibility: {
    eligible: boolean;
    code: string;
    message: string;
    override_allowed: boolean;
  };
  product: {
    product_code: string;
    terms_version: number;
    upfront_price_kopecks: number;
    success_fee_percent: number;
    success_fee_installments_count: number;
    active_support_months: number;
    probation_support_days: number;
    included_mock_interviews: number;
    offer_valid_days: number;
  };
  application: PythonRepeatApplication | null;
  enrollment: PythonRepeatEnrollment | null;
  offers: PythonRepeatEmploymentOffer[];
  obligation: null | {
    id: string;
    salary_base_kopecks: number;
    success_fee_percent: number;
    total_amount_kopecks: number;
    installments_count: number;
    status: "active" | "paid" | "cancelled";
    installments: PythonRepeatInstallment[];
  };
}

export interface AdminPythonRepeatApplication extends PythonRepeatApplication {
  student: AdminOpportunityStudent;
  eligibility: PythonRepeatDashboard["eligibility"];
  enrollment: PythonRepeatEnrollment | null;
  offers: PythonRepeatEmploymentOffer[];
  obligation: PythonRepeatDashboard["obligation"];
  revenue_received_kopecks: number;
  mentor_accrued_kopecks: number;
  mentor_paid_kopecks: number;
  gross_remainder_kopecks: number;
}

export interface AdminPythonRepeatDashboard {
  applications: AdminPythonRepeatApplication[];
  mentors: AdminOpportunityStudent[];
}
