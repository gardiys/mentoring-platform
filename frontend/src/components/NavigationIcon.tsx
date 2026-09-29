const paths = {
  roadmap: "M5 3v18m0-16h12l-2 4 2 4H5",
  book: "M12 5v16m0-16C9 3 5 3 2 4v15c3-1 7-1 10 2 3-3 7-3 10-2V4c-3-1-7-1-10 1Z",
  opportunity: "m12 3 3 6 6 1-4.5 4.5 1 6.5-5.5-3-5.5 3 1-6.5L3 10l6-1Z",
  briefcase: "M8 7V4h8v3M3 7h18v14H3Zm0 6c6 3 12 3 18 0m-9 0v4",
  cards: "M6 3h15v15M3 6h15v15H3Zm4 5h7m-7 5h4",
  analysis:
    "M14 3H4v18h16V11M8 10h3m-3 4h8m-8 3h5m4-16 1.2 3.8L22 6l-3.8 1.2L17 11l-1.2-3.8L12 6l3.8-1.2Z",
  journal: "M6 3h14v18H6ZM3 7h5m-5 5h5m-5 5h5m4-10h5m-5 5h5",
  chat: "M3 3h18v13H10l-5 5v-5H3Zm4 5h10M7 12h6",
  document: "M14 2H4v20h16V8Zm0 0v6h6M8 12h8m-8 4h6",
  video: "M3 4h18v16H3Zm6 4 7 4-7 4Z",
  contacts:
    "M4 3h16v18H4ZM2 7h4m-4 5h4m-4 5h4m3-1c0-4 10-4 10 0m-2-8a3 3 0 1 1-6 0 3 3 0 0 1 6 0",
  copilot: "M12 3v3M4 6h16v15H4Zm4 5h1m6 0h1m-8 5h8M1 11v5m22-5v5",
  question: "M3 3h18v14H10l-5 4v-4H3Zm6 5a3 3 0 1 1 4 2.8L12 12m0 2v.1",
  person: "M16 7a4 4 0 1 1-8 0 4 4 0 0 1 8 0ZM4 21v-2a8 6 0 0 1 16 0v2",
  people:
    "M14 7a4 4 0 1 1-8 0 4 4 0 0 1 8 0ZM2 21v-2c0-8 16-8 16 0v2m0-18a4 4 0 0 1 0 8m1 3c3 1 3 3 3 7",
  inbox: "M6 3h12l4 11v7H2v-7Zm-4 11h6l2 3h4l2-3h6M8 7h8m-8 3h8",
  wallet: "M20 7V3H4a2 2 0 0 0 0 4h18v14H2V5m20 7h-7v5h7m-4-2.5h.1",
  award: "M17 8A5 5 0 1 1 7 8a5 5 0 0 1 10 0ZM8 12 5 22l7-4 7 4-3-10",
  shield: "M12 2 3 6v6c0 5 9 10 9 10s9-5 9-10V6Zm-5 10 3 3 7-7",
  company: "M4 22V3h12v19m0-13h5v13M2 22h21M8 7h4m-4 4h4m-4 4h4m-3 7v-3h2v3",
  calendar: "M3 5h18v16H3Zm4-3v6m10-6v6M3 10h18M7 14h2m4 0h2m-8 3h2",
  link: "m10 13 4-4m-7 7-1 1a4 4 0 0 1-6-6l5-5a4 4 0 0 1 6 0m2 2 1-1a4 4 0 0 1 6 6l-5 5a4 4 0 0 1-6 0",
  switchUser:
    "M14 7a4 4 0 1 1-8 0 4 4 0 0 1 8 0ZM2 21v-2c0-5 7-7 11-5m3 1h6l-3-3m3 7h-6l3 3",
} as const;

const routeIcons: Record<string, keyof typeof paths> = {
  "/roadmaps": "roadmap",
  "/knowledge": "book",
  "/opportunities": "opportunity",
  "/admin/opportunities": "opportunity",
  "/career-package": "briefcase",
  "/interviews": "cards",
  "/interviews/analysis": "analysis",
  "/interviews/journal": "journal",
  "/interviews/mocks": "chat",
  "/interviews/materials": "document",
  "/interviews/catalog": "video",
  "/interviews/recruiters": "contacts",
  "/copilot": "copilot",
  "/interviews/personal-review": "question",
  "/mentor/interview-reviews": "analysis",
  "/my-mentor": "person",
  "/mentor/profile": "person",
  "/mentor/students": "people",
  "/admin/applications": "inbox",
  "/admin/students": "people",
  "/admin/mentors": "people",
  "/payments": "wallet",
  "/mentor/rewards": "award",
  "/admin/payments": "wallet",
  "/admin/card-automation/clusters": "shield",
  "/mentor/card-automation/clusters": "shield",
  "/admin/interview-question-moderation": "question",
  "/admin/company-alias-proposals": "company",
  "/admin/schedule": "calendar",
  "/admin/useful-links": "link",
  "/admin/tracks": "roadmap",
  "/admin/roadmaps": "roadmap",
  "/admin/knowledge": "book",
  "/admin/interviews": "cards",
  "/dev-login": "switchUser",
};

export function NavigationIcon({ to }: { to: string }) {
  return (
    <svg
      className="navigation-icon"
      width="22"
      height="22"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.7"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
    >
      <path d={paths[routeIcons[to] ?? "document"]} />
    </svg>
  );
}
