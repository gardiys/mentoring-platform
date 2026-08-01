import type { components } from "../api/generated/schema";

type Schemas = components["schemas"];

export type User = Schemas["UserRead"];
export type RoadmapListItem = Schemas["RoadmapListItem"];
export type RoadmapDetail = Schemas["RoadmapDetail"];
export type TopicDetail = Schemas["TopicDetail"];
export type ProgressStatus = Schemas["TopicProgressRead"]["status"];
export type ProgressUpdateResponse = Schemas["ProgressUpdateResponse"];
export type MentorStudentListItem = Schemas["MentorStudentListItem"];
export type MentorStudentDetail = Schemas["MentorStudentDetail"];
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
