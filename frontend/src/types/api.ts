import type { components } from "../api/generated/schema";

type Schemas = components["schemas"];

export type User = Schemas["UserRead"];
export type RoadmapListItem = Schemas["RoadmapListItem"];
export type RoadmapDetail = Schemas["RoadmapDetail"];
export type TopicDetail = Schemas["TopicDetail"];
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
export type AdminTopicRead = Schemas["AdminTopicRead"];
export type AdminTrackMutation = Schemas["AdminTrackMutation"];
export type AdminTrackRead = Schemas["AdminTrackRead"];
export type AdminTrackOptions = Schemas["AdminTrackOptions"];
export type AdminTrackRoadmapRead = Schemas["AdminTrackRoadmapRead"];
export type AdminTrackStudentOption = Schemas["AdminTrackStudentOption"];
export type TrackAccessRead = Schemas["TrackAccessRead"];

export type AdminStudentMutation = Omit<
  Schemas["AdminStudentMutation"],
  "last_name" | "email" | "track_ids"
> & {
  last_name: string | null;
  email: string | null;
  track_ids: string[];
  mentor_id: string | null;
};
export type AdminStudentTrackRead = Schemas["AdminStudentTrackRead"];
export interface AdminStudentMentorRead {
  id: string;
  first_name: string;
  last_name: string | null;
  telegram_username: string | null;
}
export type AdminStudentListItem = Schemas["AdminStudentListItem"] & {
  mentor: AdminStudentMentorRead | null;
};
export type AdminStudentDetail = Schemas["AdminStudentDetail"] & {
  mentor: AdminStudentMentorRead | null;
};
export type AdminStudentPage = Omit<Schemas["AdminStudentPage"], "items"> & {
  items: AdminStudentListItem[];
};
export type AdminStudentTrackOption = Schemas["AdminStudentTrackOption"];
export type AdminStudentOptions = Schemas["AdminStudentOptions"] & {
  mentors: AdminStudentMentorRead[];
};
export type KnowledgeEntryKind = Schemas["KnowledgeEntryKind"];
export type KnowledgeTopicListItem = Schemas["KnowledgeTopicListItem"];
export type KnowledgeTopicDetail = Schemas["KnowledgeTopicDetail"];
export type KnowledgeEntryDetail = Schemas["KnowledgeEntryDetail"];
export type KnowledgeSearchResult = Schemas["KnowledgeSearchResult"];
export type AdminKnowledgeEntryMutation =
  Schemas["AdminKnowledgeEntryMutation"];
export type AdminKnowledgeTopicMutation =
  Schemas["AdminKnowledgeTopicMutation"];
export type AdminKnowledgeTopicRead = Schemas["AdminKnowledgeTopicRead"];
export type AdminKnowledgeEntryRead = Schemas["AdminKnowledgeEntryRead"];
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
export type InterviewProcessDetail = Schemas["InterviewProcessDetail"];
export type CompanyOption = Schemas["CompanyOption"];
export type InterviewDirectionOption = Schemas["InterviewDirectionOption"];
export type InterviewUploadIntent = Schemas["InterviewUploadIntent"];
export type InterviewDownloadUrl = Schemas["InterviewDownloadUrl"];
export type InterviewCatalogCompanyListItem =
  Schemas["InterviewCatalogCompanyListItem"];
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

export interface InterviewCatalogFilters {
  query: string;
  authorId: string | null;
  trackId: string | null;
  stageType: InterviewStageType | null;
  hasOffer: boolean;
  mediaKind: InterviewCatalogMediaKind | null;
}

export type StudentLearningStatus =
  "learning" | "interviewing" | "probation" | "finished";
export type StudentStrengthLevel = "weak" | "medium" | "strong";
export type MentorDocumentKind = "resume" | "legend";
export type MockInterviewStatus = "planned" | "completed";

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
  learning_status: StudentLearningStatus;
  strength_level: StudentStrengthLevel | null;
  roadmaps: MentorStudentRoadmapSummary[];
  current_topics: MentorCurrentTopic[];
  last_progress_at: string | null;
  completed_topics_this_week: number;
  is_overdue: boolean;
  mock_interview_count: number;
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
