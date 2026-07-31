import { Navigate, createBrowserRouter } from "react-router-dom";

import { AppLayout } from "../components/AppLayout";
import { ProtectedLayout } from "../components/ProtectedLayout";
import { AdminRoadmapCreatePage } from "../pages/AdminRoadmapCreatePage";
import { AdminRoadmapEditPage } from "../pages/AdminRoadmapEditPage";
import { AdminRoadmapsPage } from "../pages/AdminRoadmapsPage";
import { AdminTrackCreatePage } from "../pages/AdminTrackCreatePage";
import { AdminTrackEditPage } from "../pages/AdminTrackEditPage";
import { AdminTracksPage } from "../pages/AdminTracksPage";
import { AdminKnowledgeTopicCreatePage } from "../pages/AdminKnowledgeTopicCreatePage";
import { AdminKnowledgeTopicEditPage } from "../pages/AdminKnowledgeTopicEditPage";
import { AdminKnowledgeTopicsPage } from "../pages/AdminKnowledgeTopicsPage";
import { AdminInterviewDeckCreatePage } from "../pages/AdminInterviewDeckCreatePage";
import { AdminInterviewDeckEditPage } from "../pages/AdminInterviewDeckEditPage";
import { AdminInterviewDecksPage } from "../pages/AdminInterviewDecksPage";
import { DevLoginPage } from "../pages/DevLoginPage";
import { MentorStudentPage } from "../pages/MentorStudentPage";
import { MentorStudentsPage } from "../pages/MentorStudentsPage";
import { KnowledgeBasePage } from "../pages/KnowledgeBasePage";
import { KnowledgeEntryPage } from "../pages/KnowledgeEntryPage";
import { KnowledgeTopicPage } from "../pages/KnowledgeTopicPage";
import { InterviewsPage } from "../pages/InterviewsPage";
import { InterviewStudyPage } from "../pages/InterviewStudyPage";
import { NotFoundPage } from "../pages/NotFoundPage";
import { OnboardingPage } from "../pages/OnboardingPage";
import { RoadmapPage } from "../pages/RoadmapPage";
import { RoadmapsPage } from "../pages/RoadmapsPage";
import { TopicPage } from "../pages/TopicPage";

export const router = createBrowserRouter([
  { path: "/dev-login", element: <DevLoginPage /> },
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
          {
            path: "/interviews/:deckSlug",
            element: <InterviewStudyPage />,
          },
          { path: "/mentor/students", element: <MentorStudentsPage /> },
          {
            path: "/mentor/students/:studentId",
            element: <MentorStudentPage />,
          },
          { path: "/admin/roadmaps", element: <AdminRoadmapsPage /> },
          { path: "/admin/roadmaps/new", element: <AdminRoadmapCreatePage /> },
          {
            path: "/admin/roadmaps/:roadmapId/edit",
            element: <AdminRoadmapEditPage />,
          },
          { path: "/admin/tracks", element: <AdminTracksPage /> },
          { path: "/admin/tracks/new", element: <AdminTrackCreatePage /> },
          {
            path: "/admin/tracks/:trackId/edit",
            element: <AdminTrackEditPage />,
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
            path: "/admin/interviews",
            element: <AdminInterviewDecksPage />,
          },
          {
            path: "/admin/interviews/new",
            element: <AdminInterviewDeckCreatePage />,
          },
          {
            path: "/admin/interviews/:deckId/edit",
            element: <AdminInterviewDeckEditPage />,
          },
        ],
      },
    ],
  },
  { path: "*", element: <NotFoundPage /> },
]);
