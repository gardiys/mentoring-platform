import { Navigate, createBrowserRouter } from "react-router-dom";

import { AppLayout } from "../components/AppLayout";
import { LoadingState } from "../components/LoadingState";
import { ProtectedLayout } from "../components/ProtectedLayout";
import { RoleGuard } from "../components/RoleGuard";
import { RouteErrorBoundary } from "../components/RouteErrorBoundary";
import { lazyPage } from "./lazyRoute";

const studentRoutes = [
  {
    path: "/roadmaps",
    lazy: lazyPage(() => import("../pages/RoadmapsPage"), "RoadmapsPage"),
  },
  {
    path: "/roadmaps/:roadmapSlug",
    lazy: lazyPage(() => import("../pages/RoadmapPage"), "RoadmapPage"),
  },
  {
    path: "/topics/:topicId",
    lazy: lazyPage(() => import("../pages/TopicPage"), "TopicPage"),
  },
  {
    path: "/knowledge",
    lazy: lazyPage(
      () => import("../pages/KnowledgeBasePage"),
      "KnowledgeBasePage",
    ),
  },
  {
    path: "/knowledge/topics/:topicSlug",
    lazy: lazyPage(
      () => import("../pages/KnowledgeTopicPage"),
      "KnowledgeTopicPage",
    ),
  },
  {
    path: "/knowledge/entries/:entrySlug",
    lazy: lazyPage(
      () => import("../pages/KnowledgeEntryPage"),
      "KnowledgeEntryPage",
    ),
  },
  {
    path: "/interviews",
    lazy: lazyPage(() => import("../pages/InterviewsPage"), "InterviewsPage"),
  },
  {
    path: "/interviews/catalog",
    lazy: lazyPage(
      () => import("../pages/InterviewCatalogPage"),
      "InterviewCatalogPage",
    ),
  },
  {
    path: "/interviews/catalog/history",
    lazy: lazyPage(
      () => import("../pages/InterviewCatalogHistoryPage"),
      "InterviewCatalogHistoryPage",
    ),
  },
  {
    path: "/interviews/catalog/:companyId",
    lazy: lazyPage(
      () => import("../pages/InterviewCatalogCompanyPage"),
      "InterviewCatalogCompanyPage",
    ),
  },
  {
    path: "/interviews/journal/new",
    lazy: lazyPage(
      () => import("../pages/InterviewProcessCreatePage"),
      "InterviewProcessCreatePage",
    ),
  },
  {
    path: "/interviews/journal/:processId",
    lazy: lazyPage(
      () => import("../pages/InterviewProcessPage"),
      "InterviewProcessPage",
    ),
  },
  {
    path: "/interviews/analysis/:interviewId",
    lazy: lazyPage(
      () => import("../pages/InterviewIntelligencePage"),
      "InterviewIntelligencePage",
    ),
  },
  {
    path: "/interviews/:deckSlug",
    lazy: lazyPage(
      () => import("../pages/InterviewStudyPage"),
      "InterviewStudyPage",
    ),
  },
];

const mentorRoutes = [
  {
    path: "/mentor/profile",
    lazy: lazyPage(
      () => import("../pages/MentorProfilePage"),
      "MentorProfilePage",
    ),
  },
  {
    path: "/mentor/students",
    lazy: lazyPage(
      () => import("../pages/MentorStudentsPage"),
      "MentorStudentsPage",
    ),
  },
  {
    path: "/mentor/interview-reviews",
    lazy: lazyPage(
      () => import("../pages/MentorInterviewIntelligencePage"),
      "MentorInterviewIntelligencePage",
    ),
  },
  {
    path: "/mentor/interview-reviews/:interviewId",
    lazy: lazyPage(
      () => import("../pages/InterviewIntelligencePage"),
      "InterviewIntelligencePage",
    ),
  },
  {
    path: "/mentor/students/:studentId",
    lazy: lazyPage(
      () => import("../pages/MentorStudentPage"),
      "MentorStudentPage",
    ),
  },
  {
    path: "/mentor/students/:studentId/interviews/:processId",
    lazy: lazyPage(
      () => import("../pages/MentorInterviewPage"),
      "MentorInterviewPage",
    ),
  },
];

const adminRoutes = [
  {
    path: "/admin/schedule",
    lazy: lazyPage(
      () => import("../pages/AdminSchedulePage"),
      "AdminSchedulePage",
    ),
  },
  {
    path: "/admin/useful-links",
    lazy: lazyPage(
      () => import("../pages/AdminUsefulLinksPage"),
      "AdminUsefulLinksPage",
    ),
  },
  {
    path: "/admin/roadmaps",
    lazy: lazyPage(
      () => import("../pages/AdminRoadmapsPage"),
      "AdminRoadmapsPage",
    ),
  },
  {
    path: "/admin/roadmaps/new",
    lazy: lazyPage(
      () => import("../pages/AdminRoadmapCreatePage"),
      "AdminRoadmapCreatePage",
    ),
  },
  {
    path: "/admin/roadmaps/:roadmapId/edit",
    lazy: lazyPage(
      () => import("../pages/AdminRoadmapEditPage"),
      "AdminRoadmapEditPage",
    ),
  },
  {
    path: "/admin/roadmaps/:roadmapId/sections/:sectionId/edit",
    lazy: lazyPage(
      () => import("../pages/AdminRoadmapSectionEditPage"),
      "AdminRoadmapSectionEditPage",
    ),
  },
  {
    path: "/admin/roadmaps/:roadmapId/sections/new",
    lazy: lazyPage(
      () => import("../pages/AdminRoadmapSectionEditPage"),
      "AdminRoadmapSectionEditPage",
    ),
  },
  {
    path: "/admin/roadmaps/:roadmapId/sections/:sectionId/topics/new",
    lazy: lazyPage(
      () => import("../pages/AdminRoadmapTopicEditPage"),
      "AdminRoadmapTopicEditPage",
    ),
  },
  {
    path: "/admin/roadmaps/:roadmapId/sections/:sectionId/topics/:topicId/edit",
    lazy: lazyPage(
      () => import("../pages/AdminRoadmapTopicEditPage"),
      "AdminRoadmapTopicEditPage",
    ),
  },
  {
    path: "/admin/tracks",
    lazy: lazyPage(() => import("../pages/AdminTracksPage"), "AdminTracksPage"),
  },
  {
    path: "/admin/tracks/new",
    lazy: lazyPage(
      () => import("../pages/AdminTrackCreatePage"),
      "AdminTrackCreatePage",
    ),
  },
  {
    path: "/admin/tracks/:trackId/edit",
    lazy: lazyPage(
      () => import("../pages/AdminTrackEditPage"),
      "AdminTrackEditPage",
    ),
  },
  {
    path: "/admin/students",
    lazy: lazyPage(
      () => import("../pages/AdminStudentsPage"),
      "AdminStudentsPage",
    ),
  },
  {
    path: "/admin/mentors",
    lazy: lazyPage(
      () => import("../pages/AdminMentorsPage"),
      "AdminMentorsPage",
    ),
  },
  {
    path: "/admin/students/new",
    lazy: lazyPage(
      () => import("../pages/AdminStudentCreatePage"),
      "AdminStudentCreatePage",
    ),
  },
  {
    path: "/admin/students/:studentId/edit",
    lazy: lazyPage(
      () => import("../pages/AdminStudentEditPage"),
      "AdminStudentEditPage",
    ),
  },
  {
    path: "/admin/knowledge",
    lazy: lazyPage(
      () => import("../pages/AdminKnowledgeTopicsPage"),
      "AdminKnowledgeTopicsPage",
    ),
  },
  {
    path: "/admin/knowledge/new",
    lazy: lazyPage(
      () => import("../pages/AdminKnowledgeTopicCreatePage"),
      "AdminKnowledgeTopicCreatePage",
    ),
  },
  {
    path: "/admin/knowledge/:topicId/edit",
    lazy: lazyPage(
      () => import("../pages/AdminKnowledgeTopicEditPage"),
      "AdminKnowledgeTopicEditPage",
    ),
  },
  {
    path: "/admin/knowledge/:topicId/entries/new",
    lazy: lazyPage(
      () => import("../pages/AdminKnowledgeEntryEditPage"),
      "AdminKnowledgeEntryEditPage",
    ),
  },
  {
    path: "/admin/knowledge/:topicId/entries/:entryId/edit",
    lazy: lazyPage(
      () => import("../pages/AdminKnowledgeEntryEditPage"),
      "AdminKnowledgeEntryEditPage",
    ),
  },
  {
    path: "/admin/interviews",
    lazy: lazyPage(
      () => import("../pages/AdminInterviewDecksPage"),
      "AdminInterviewDecksPage",
    ),
  },
  {
    path: "/admin/interview-question-moderation",
    lazy: lazyPage(
      () => import("../pages/AdminInterviewQuestionModerationPage"),
      "AdminInterviewQuestionModerationPage",
    ),
  },
  {
    path: "/admin/interview-question-moderation/:questionId",
    lazy: lazyPage(
      () => import("../pages/AdminInterviewQuestionModerationEditPage"),
      "AdminInterviewQuestionModerationEditPage",
    ),
  },
  {
    path: "/admin/interviews/new",
    lazy: lazyPage(
      () => import("../pages/AdminInterviewDeckCreatePage"),
      "AdminInterviewDeckCreatePage",
    ),
  },
  {
    path: "/admin/interviews/:deckId/edit",
    lazy: lazyPage(
      () => import("../pages/AdminInterviewDeckEditPage"),
      "AdminInterviewDeckEditPage",
    ),
  },
  {
    path: "/admin/interviews/:deckId/cards/new",
    lazy: lazyPage(
      () => import("../pages/AdminInterviewCardEditPage"),
      "AdminInterviewCardEditPage",
    ),
  },
  {
    path: "/admin/interviews/:deckId/cards/:cardId/edit",
    lazy: lazyPage(
      () => import("../pages/AdminInterviewCardEditPage"),
      "AdminInterviewCardEditPage",
    ),
  },
];

export const router = createBrowserRouter([
  {
    ErrorBoundary: RouteErrorBoundary,
    HydrateFallback: () => <LoadingState label="Загружаем платформу…" />,
    children: [
      {
        path: "/dev-login",
        ...(import.meta.env.DEV
          ? {
              lazy: lazyPage(
                () => import("../pages/DevLoginPage"),
                "DevLoginPage",
              ),
            }
          : { element: <Navigate to="/login" replace /> }),
      },
      {
        path: "/login",
        lazy: lazyPage(
          () => import("../pages/TelegramRequiredPage"),
          "TelegramRequiredPage",
        ),
      },
      {
        path: "/telegram-required",
        element: <Navigate to="/login" replace />,
      },
      {
        element: <ProtectedLayout />,
        children: [
          {
            path: "/onboarding",
            lazy: lazyPage(
              () => import("../pages/OnboardingPage"),
              "OnboardingPage",
            ),
          },
          {
            element: <AppLayout />,
            children: [
              { path: "/", element: <Navigate to="/roadmaps" replace /> },
              ...studentRoutes,
              {
                element: <RoleGuard roles={["student"]} />,
                children: [
                  {
                    path: "/my-mentor",
                    lazy: lazyPage(
                      () => import("../pages/MyMentorPage"),
                      "MyMentorPage",
                    ),
                  },
                ],
              },
              {
                element: <RoleGuard roles={["mentor", "admin"]} />,
                children: mentorRoutes,
              },
              {
                element: <RoleGuard roles={["admin"]} />,
                children: adminRoutes,
              },
            ],
          },
        ],
      },
      {
        path: "*",
        lazy: lazyPage(() => import("../pages/NotFoundPage"), "NotFoundPage"),
      },
    ],
  },
]);
