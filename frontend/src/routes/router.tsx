import { Navigate, createBrowserRouter } from "react-router-dom";

import { AppLayout } from "../components/AppLayout";
import { ProtectedLayout } from "../components/ProtectedLayout";
import { AdminRoadmapCreatePage } from "../pages/AdminRoadmapCreatePage";
import { AdminRoadmapEditPage } from "../pages/AdminRoadmapEditPage";
import { AdminRoadmapSectionEditPage } from "../pages/AdminRoadmapSectionEditPage";
import { AdminRoadmapTopicEditPage } from "../pages/AdminRoadmapTopicEditPage";
import { AdminRoadmapsPage } from "../pages/AdminRoadmapsPage";
import { AdminTrackCreatePage } from "../pages/AdminTrackCreatePage";
import { AdminTrackEditPage } from "../pages/AdminTrackEditPage";
import { AdminTracksPage } from "../pages/AdminTracksPage";
import { AdminStudentCreatePage } from "../pages/AdminStudentCreatePage";
import { AdminStudentEditPage } from "../pages/AdminStudentEditPage";
import { AdminStudentsPage } from "../pages/AdminStudentsPage";
import { AdminMentorsPage } from "../pages/AdminMentorsPage";
import { AdminKnowledgeTopicCreatePage } from "../pages/AdminKnowledgeTopicCreatePage";
import { AdminKnowledgeTopicEditPage } from "../pages/AdminKnowledgeTopicEditPage";
import { AdminKnowledgeEntryEditPage } from "../pages/AdminKnowledgeEntryEditPage";
import { AdminKnowledgeTopicsPage } from "../pages/AdminKnowledgeTopicsPage";
import { AdminInterviewDeckCreatePage } from "../pages/AdminInterviewDeckCreatePage";
import { AdminInterviewDeckEditPage } from "../pages/AdminInterviewDeckEditPage";
import { AdminInterviewCardEditPage } from "../pages/AdminInterviewCardEditPage";
import { AdminInterviewDecksPage } from "../pages/AdminInterviewDecksPage";
import { AdminInterviewQuestionModerationPage } from "../pages/AdminInterviewQuestionModerationPage";
import { AdminInterviewQuestionModerationEditPage } from "../pages/AdminInterviewQuestionModerationEditPage";
import { DevLoginPage } from "../pages/DevLoginPage";
import { MentorStudentPage } from "../pages/MentorStudentPage";
import { MentorStudentsPage } from "../pages/MentorStudentsPage";
import { MentorInterviewPage } from "../pages/MentorInterviewPage";
import { KnowledgeBasePage } from "../pages/KnowledgeBasePage";
import { KnowledgeEntryPage } from "../pages/KnowledgeEntryPage";
import { KnowledgeTopicPage } from "../pages/KnowledgeTopicPage";
import { InterviewsPage } from "../pages/InterviewsPage";
import { InterviewStudyPage } from "../pages/InterviewStudyPage";
import { InterviewProcessCreatePage } from "../pages/InterviewProcessCreatePage";
import { InterviewProcessPage } from "../pages/InterviewProcessPage";
import { InterviewCatalogPage } from "../pages/InterviewCatalogPage";
import { InterviewCatalogCompanyPage } from "../pages/InterviewCatalogCompanyPage";
import { InterviewIntelligencePage } from "../pages/InterviewIntelligencePage";
import { MentorInterviewIntelligencePage } from "../pages/MentorInterviewIntelligencePage";
import { NotFoundPage } from "../pages/NotFoundPage";
import { OnboardingPage } from "../pages/OnboardingPage";
import { RoadmapPage } from "../pages/RoadmapPage";
import { RoadmapsPage } from "../pages/RoadmapsPage";
import { TopicPage } from "../pages/TopicPage";
import { TelegramRequiredPage } from "../pages/TelegramRequiredPage";

export const router = createBrowserRouter([
  {
    path: "/dev-login",
    element: import.meta.env.DEV ? (
      <DevLoginPage />
    ) : (
      <Navigate to="/login" replace />
    ),
  },
  { path: "/login", element: <TelegramRequiredPage /> },
  { path: "/telegram-required", element: <Navigate to="/login" replace /> },
  {
    element: <ProtectedLayout />,
    children: [
      { path: "/onboarding", element: <OnboardingPage /> },
      {
        element: <AppLayout />,
        children: [
          { path: "/", element: <Navigate to="/roadmaps" replace /> },
          { path: "/roadmaps", element: <RoadmapsPage /> },
          { path: "/roadmaps/:roadmapSlug", element: <RoadmapPage /> },
          { path: "/topics/:topicId", element: <TopicPage /> },
          { path: "/knowledge", element: <KnowledgeBasePage /> },
          {
            path: "/knowledge/topics/:topicSlug",
            element: <KnowledgeTopicPage />,
          },
          {
            path: "/knowledge/entries/:entrySlug",
            element: <KnowledgeEntryPage />,
          },
          { path: "/interviews", element: <InterviewsPage /> },
          { path: "/interviews/catalog", element: <InterviewCatalogPage /> },
          {
            path: "/interviews/catalog/:companyId",
            element: <InterviewCatalogCompanyPage />,
          },
          {
            path: "/interviews/journal/new",
            element: <InterviewProcessCreatePage />,
          },
          {
            path: "/interviews/journal/:processId",
            element: <InterviewProcessPage />,
          },
          {
            path: "/interviews/analysis/:interviewId",
            element: <InterviewIntelligencePage />,
          },
          {
            path: "/interviews/:deckSlug",
            element: <InterviewStudyPage />,
          },
          { path: "/mentor/students", element: <MentorStudentsPage /> },
          {
            path: "/mentor/interview-reviews",
            element: <MentorInterviewIntelligencePage />,
          },
          {
            path: "/mentor/interview-reviews/:interviewId",
            element: <InterviewIntelligencePage />,
          },
          {
            path: "/mentor/students/:studentId",
            element: <MentorStudentPage />,
          },
          {
            path: "/mentor/students/:studentId/interviews/:processId",
            element: <MentorInterviewPage />,
          },
          { path: "/admin/roadmaps", element: <AdminRoadmapsPage /> },
          { path: "/admin/roadmaps/new", element: <AdminRoadmapCreatePage /> },
          {
            path: "/admin/roadmaps/:roadmapId/edit",
            element: <AdminRoadmapEditPage />,
          },
          {
            path: "/admin/roadmaps/:roadmapId/sections/:sectionId/edit",
            element: <AdminRoadmapSectionEditPage />,
          },
          {
            path: "/admin/roadmaps/:roadmapId/sections/new",
            element: <AdminRoadmapSectionEditPage />,
          },
          {
            path: "/admin/roadmaps/:roadmapId/sections/:sectionId/topics/new",
            element: <AdminRoadmapTopicEditPage />,
          },
          {
            path: "/admin/roadmaps/:roadmapId/sections/:sectionId/topics/:topicId/edit",
            element: <AdminRoadmapTopicEditPage />,
          },
          { path: "/admin/tracks", element: <AdminTracksPage /> },
          { path: "/admin/tracks/new", element: <AdminTrackCreatePage /> },
          {
            path: "/admin/tracks/:trackId/edit",
            element: <AdminTrackEditPage />,
          },
          { path: "/admin/students", element: <AdminStudentsPage /> },
          { path: "/admin/mentors", element: <AdminMentorsPage /> },
          {
            path: "/admin/students/new",
            element: <AdminStudentCreatePage />,
          },
          {
            path: "/admin/students/:studentId/edit",
            element: <AdminStudentEditPage />,
          },
          { path: "/admin/knowledge", element: <AdminKnowledgeTopicsPage /> },
          {
            path: "/admin/knowledge/new",
            element: <AdminKnowledgeTopicCreatePage />,
          },
          {
            path: "/admin/knowledge/:topicId/edit",
            element: <AdminKnowledgeTopicEditPage />,
          },
          {
            path: "/admin/knowledge/:topicId/entries/new",
            element: <AdminKnowledgeEntryEditPage />,
          },
          {
            path: "/admin/knowledge/:topicId/entries/:entryId/edit",
            element: <AdminKnowledgeEntryEditPage />,
          },
          {
            path: "/admin/interviews",
            element: <AdminInterviewDecksPage />,
          },
          {
            path: "/admin/interview-question-moderation",
            element: <AdminInterviewQuestionModerationPage />,
          },
          {
            path: "/admin/interview-question-moderation/:questionId",
            element: <AdminInterviewQuestionModerationEditPage />,
          },
          {
            path: "/admin/interviews/new",
            element: <AdminInterviewDeckCreatePage />,
          },
          {
            path: "/admin/interviews/:deckId/edit",
            element: <AdminInterviewDeckEditPage />,
          },
          {
            path: "/admin/interviews/:deckId/cards/new",
            element: <AdminInterviewCardEditPage />,
          },
          {
            path: "/admin/interviews/:deckId/cards/:cardId/edit",
            element: <AdminInterviewCardEditPage />,
          },
        ],
      },
    ],
  },
  { path: "*", element: <NotFoundPage /> },
]);
