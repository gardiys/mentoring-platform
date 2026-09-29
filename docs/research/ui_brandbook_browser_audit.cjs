// Run from repository root; API requests are fulfilled with local test fixtures.
// See docs/audits/ui-brandbook-v4.md for dependencies and invocation.
const baseUrl = process.env.UI_AUDIT_URL || "http://127.0.0.1:5173";
const outputDir =
  process.env.UI_AUDIT_OUTPUT_DIR ||
  require("node:path").join(require("node:os").tmpdir(), "mentoring-ui-audit");
require("node:fs").mkdirSync(outputDir, { recursive: true });
const { chromium } = require(
  process.env.PLAYWRIGHT_MODULE_PATH || "playwright",
);
const fs = require("fs"),
  vm = require("vm"),
  ts = require(process.cwd() + "/frontend/node_modules/typescript");
const root = process.cwd();
function fixture(file, names) {
  const text = fs
    .readFileSync(root + "/frontend/tests/" + file, "utf8")
    .split("afterEach(")[0];
  const sf = ts.createSourceFile(file, text, 99, true, 4);
  const src = sf.statements
    .filter(ts.isVariableStatement)
    .map((n) => n.getText(sf))
    .join("\n");
  const context = {};
  vm.runInNewContext(
    ts.transpile(src + ";globalThis.result={" + names.join(",") + "}", {
      target: 99,
    }),
    context,
  );
  return JSON.parse(JSON.stringify(context.result));
}
const study = fixture("interviews.test.tsx", [
  "deck",
  "topics",
  "session",
  "questionTable",
]);
const knowledge = fixture("knowledge.test.tsx", ["topic", "entry"]);
const recruiters = fixture("interview-recruiters.test.tsx", [
  "student",
  "groupedRecruiters",
  "daily",
]);
const intelligence = fixture("interview-intelligence-detail.test.tsx", [
  "detail",
]);
const catalog = fixture("interview-catalog.test.tsx", ["company"]);
const automation = fixture("card-automation.test.tsx", ["cluster"]);
const queue = fixture("interview-intelligence-admin.test.tsx", [
  "requestedInterview",
  "operations",
]);
const report = { pages: [], errors: [], unhandled: [], controls: [] };
(async () => {
  const browser = await chromium.launch({
    executablePath: process.env.CHROME_BIN || undefined,
    headless: true,
  });
  const page = await browser.newPage();
  page.on("pageerror", (e) => report.errors.push(e.message));
  await page.addInitScript(() => {
    window.loadingLogoFlashes = 0;
    new MutationObserver(() => {
      if (document.querySelector(".loading-state .brand-mark"))
        window.loadingLogoFlashes++;
    }).observe(document, { subtree: true, childList: true });
  });
  let role = "student",
    login = false;
  await page.route("**/api/v1/**", async (r) => {
    const p = new URL(r.request().url()).pathname;
    let body,
      status = 200;
    if (p === "/api/v1/me") {
      body = login
        ? { detail: { code: "unauthorized", message: "Unauthorized" } }
        : { ...recruiters.student, role };
      if (login) status = 401;
    } else if (p.includes("/notifications"))
      body = { items: [], unread_count: 0, total: 0, limit: 20, offset: 0 };
    else if (p === "/api/v1/copilot/access")
      body = { allowed: true, student_allowed: true, students_enabled: true };
    else if (p === "/api/v1/roadmaps")
      body = [
        {
          id: "r1",
          title: "Python Backend",
          slug: "python-backend",
          description: "Практика, теория и подготовка к собеседованиям.",
          completed_topics: 12,
          total_topics: 40,
          progress_percent: 30,
          started_at: null,
          total_duration_days: 100,
        },
      ];
    else if (p === "/api/v1/admin/tracks") body = [];
    else if (p === "/api/v1/admin/card-automation/clusters")
      body = { items: [automation.cluster], total: 1, limit: 20, offset: 0 };
    else if (p === "/api/v1/knowledge/topics") body = [knowledge.topic];
    else if (p.startsWith("/api/v1/knowledge/entries/")) body = knowledge.entry;
    else if (p === "/api/v1/interviews")
      body = { items: [], total: 0, limit: 6, offset: 0 };
    else if (p === "/api/v1/interviews/decks") body = [study.deck];
    else if (p.endsWith("/session")) body = study.session;
    else if (p.endsWith("/topics")) body = study.topics;
    else if (p.endsWith("/questions")) body = study.questionTable;
    else if (
      [
        "/api/v1/interviews/journal/tracks",
        "/api/v1/mentor/me/mock-interviews",
        "/api/v1/mentor/me/documents",
      ].includes(p)
    )
      body = [];
    else if (p === "/api/v1/interviews/catalog/directions")
      body = [{ id: "t1", slug: "python", title: "Python" }];
    else if (p === "/api/v1/interviews/catalog/authors") body = [];
    else if (p === "/api/v1/interviews/catalog/companies")
      body = { items: [catalog.company], total: 1, limit: 24, offset: 0 };
    else if (p === "/api/v1/interviews/recruiters")
      body = {
        items: recruiters.groupedRecruiters,
        daily: recruiters.daily,
        total: 1,
        limit: 24,
        offset: 0,
      };
    else if (p.includes(intelligence.detail.id)) body = intelligence.detail;
    else {
      report.unhandled.push(p);
      body = [];
    }
    await r.fulfill({
      status,
      contentType: "application/json",
      body: JSON.stringify(body),
    });
  });
  async function inspect(label) {
    const result = await page.evaluate(() => {
      const canvas = document.createElement("canvas");
      canvas.width = canvas.height = 1;
      const ctx = canvas.getContext("2d", { willReadFrequently: true });
      function rgba(color) {
        ctx.clearRect(0, 0, 1, 1);
        ctx.fillStyle = color;
        ctx.fillRect(0, 0, 1, 1);
        return Array.from(ctx.getImageData(0, 0, 1, 1).data).map((v, i) =>
          i === 3 ? v / 255 : v,
        );
      }
      function composite(f, b) {
        return f
          .slice(0, 3)
          .map((v, i) => v * f[3] + b[i] * (1 - f[3]))
          .concat(1);
      }
      function background(e) {
        if (!e) return [255, 255, 255, 1];
        // The brighter endpoint is the worst case for white text on this gradient.
        if (e.classList.contains("brand-hero"))
          return rgba(getComputedStyle(e).getPropertyValue("--c-hero-start"));
        let c = rgba(getComputedStyle(e).backgroundColor);
        return c[3] === 1 ? c : composite(c, background(e.parentElement));
      }
      function lum(c) {
        return c
          .slice(0, 3)
          .map((x) => x / 255)
          .map((x) => (x <= 0.04045 ? x / 12.92 : ((x + 0.055) / 1.055) ** 2.4))
          .reduce((s, x, i) => s + x * [0.2126, 0.7152, 0.0722][i], 0);
      }
      const low = [],
        clipped = [];
      for (const e of document.querySelectorAll(
        ".brand-hero h1,.brand-hero .mantine-Text-root,.mantine-Button-label,.mantine-Button-label .mantine-Text-root,.mantine-Badge-label,.mantine-Alert-title,.mantine-NavLink-description",
      )) {
        if (
          !e.checkVisibility() ||
          e.closest("[inert],:disabled,[data-disabled],[data-loading]")
        )
          continue;
        const s = getComputedStyle(e),
          a = lum(rgba(s.color)),
          b = lum(background(e));
        const contrast = (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05);
        const min =
          parseFloat(s.fontSize) >= 24 ||
          (parseFloat(s.fontSize) >= 18.66 && Number(s.fontWeight) >= 700)
            ? 3
            : 4.5;
        if (contrast < min - 0.05)
          low.push({
            text: e.textContent.slice(0, 80),
            contrast: Number(contrast.toFixed(2)),
            color: s.color,
            bg: background(e),
          });
        if (
          e.scrollWidth > e.clientWidth + 2 &&
          e.classList.contains("mantine-Button-label")
        )
          clipped.push({
            text: e.textContent.slice(0, 100),
            width: e.clientWidth,
            scroll: e.scrollWidth,
          });
      }
      return {
        statusBackgrounds: [
          ...document.querySelectorAll(
            ".queue-status-summary .mantine-Badge-root",
          ),
        ].map((e) => getComputedStyle(e).backgroundColor),
        h1Count: document.querySelectorAll("h1").length,
        ratingHeight:
          document
            .querySelector(".interview-rating-grid")
            ?.getBoundingClientRect().height ?? 0,
        headerTargets: [
          ...document.querySelectorAll(
            ".brand-header .mantine-ActionIcon-root, .brand-header .mantine-Burger-root",
          ),
        ]
          .filter((e) => e.checkVisibility())
          .map((e) => {
            const r = e.getBoundingClientRect();
            return { width: r.width, height: r.height };
          }),
        loadingLogoFlashes: window.loadingLogoFlashes,
        width: innerWidth,
        scroll: document.documentElement.scrollWidth,
        low,
        clipped,
      };
    });
    report.pages.push({ label, ...result });
  }
  const routes = [
    ["roadmaps", "/roadmaps", "Мои роадмапы"],
    ["knowledge", "/knowledge", "Основы Backend"],
    ["interviews", "/interviews", "Вопросы с собеседований"],
    ["journal", "/interviews/journal", "Дневник собеседований"],
    ["analyses", "/interviews/analysis", "AI-разборы собеседований"],
    ["mocks", "/interviews/mocks", "Мок-собеседования"],
    ["materials", "/interviews/materials", "Резюме и легенда"],
    ["study", "/interviews/python-interview", "Что такое GIL?"],
    ["questions", "/interviews/python-interview/questions", "Таблица вопросов"],
    ["catalog", "/interviews/catalog", "Каталог компаний"],
    ["recruiters", "/interviews/recruiters", "@yandex_recruiter"],
    ["analysis", "/interviews/analysis/" + intelligence.detail.id, "Вердикт"],
    ["clusters", "/admin/card-automation/clusters", "Как работает GIL?"],
    ["login", "/login", "Продолжить через Telegram"],
    ["dev-login", "/dev-login", "Development-вход"],
  ];
  for (const theme of ["dark"]) {
    await page.addInitScript(
      (t) => localStorage.setItem("mentoring-platform-color-scheme-v2", t),
      theme,
    );
    for (const [name, url, marker] of routes) {
      if (
        process.env.UI_AUDIT_PAGES &&
        !process.env.UI_AUDIT_PAGES.split(",").includes(name)
      )
        continue;
      login = name.includes("login");
      role = name === "clusters" ? "admin" : "student";
      await page.setViewportSize({ width: 1440, height: 1000 });
      await page.goto(baseUrl + url);
      await page.getByText(marker, { exact: true }).first().waitFor();
      if (
        ["interviews", "journal", "analyses", "mocks", "materials"].includes(
          name,
        )
      )
        await page
          .getByRole("heading", { name: marker, exact: true })
          .waitFor();
      await page.evaluate(() => document.fonts.ready);
      if (name === "study")
        await page
          .getByRole("button", { name: "Показать ответ", exact: true })
          .click();
      for (const width of [1440, 768, 375, 320]) {
        await page.setViewportSize({ width, height: 950 });
        await page.waitForTimeout(300);
        await inspect(name + "-" + theme);
        if (
          (width === 1440 || width === 375) &&
          [
            "roadmaps",
            "study",
            "login",
            "dev-login",
            "analysis",
            "recruiters",
          ].includes(name)
        ) {
          await page.evaluate(() => scrollTo(0, 0));
          await page.screenshot({
            path: `${outputDir}/ui-${name}-${theme}-${width}.png`,
            fullPage: true,
          });
        }
      }
    }
  }
  // Render favicon as an image, where embedded fonts are unavailable.
  await page.goto(baseUrl + "/dev-login");
  report.favicon = await page.evaluate(async () => {
    const im = new Image();
    im.src = "/brand/mark.svg?v=2";
    await im.decode();
    const c = document.createElement("canvas");
    c.width = c.height = 16;
    const ctx = c.getContext("2d");
    ctx.drawImage(im, 0, 0, 16, 16);
    const data = ctx.getImageData(0, 0, 16, 16).data;
    let white = 0,
      yellow = 0;
    for (let i = 0; i < data.length; i += 4) {
      if (data[i] > 220 && data[i + 1] > 220 && data[i + 2] > 220) white++;
      if (data[i] > 220 && data[i + 1] > 150 && data[i + 2] < 120) yellow++;
    }
    return { white, yellow };
  });
  login = false;
  role = "admin";
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto(baseUrl + "/roadmaps");
  await page.getByText("Мои роадмапы", { exact: true }).waitFor();
  report.moderationLinks = await page
    .locator('a[href="/admin/card-automation/clusters"]')
    .count();
  report.mascotNote = await page
    .getByText("Геральт рядом", { exact: true })
    .count();
  await page.setViewportSize({ width: 375, height: 812 });
  await page.waitForTimeout(350);
  const nav = page.locator("#platform-navigation");
  report.closedMenuInert = (await nav.getAttribute("inert")) !== null;
  await page.getByRole("button", { name: "Открыть меню" }).click();
  await page.waitForTimeout(300);
  await nav
    .getByRole("link", { name: /Роадмапы/ })
    .first()
    .focus();
  await page.keyboard.press("Escape");
  report.escapeClosed =
    (await page.getByRole("button", { name: "Открыть меню" }).count()) === 1;
  report.focusReturned = await page
    .getByRole("button", { name: "Открыть меню" })
    .evaluate((e) => document.activeElement === e);
  // Cold queues: delay API responses and verify that controls never unmount or shift.
  await page.route("**/api/v1/admin/interviews/ai-operations", (r) =>
    r.fulfill({ json: queue.operations }),
  );
  await page.route("**/api/v1/mentor/interviews?*", async (r) => {
    const status = new URL(r.request().url()).searchParams.get("status");
    await new Promise((resolve) => setTimeout(resolve, 700));
    const items =
      status === "requested"
        ? Array.from({ length: 5 }, (_, index) => ({
            ...queue.requestedInterview,
            id: queue.requestedInterview.id + index,
          }))
        : [];
    await r.fulfill({
      json: { items, total: items.length, limit: 10, offset: 0 },
    });
  });
  report.queueTransitions = [];
  for (const width of [1440, 375]) {
    await page.setViewportSize({ width, height: 900 });
    await page.goto(baseUrl + "/mentor/interview-reviews");
    await page.getByText("Яндекс", { exact: true }).first().waitFor();
    await page.evaluate(() => document.fonts.ready);
    const control =
      width > 768
        ? page.locator(".mantine-SegmentedControl-root")
        : page.getByRole("textbox", { name: "Статус очереди" });
    const before = await control.boundingBox();
    for (const label of ["Проверено", "В обработке", "Все"]) {
      if (width > 768) await control.getByText(label, { exact: true }).click();
      else {
        await control.click();
        await page.getByRole("option", { name: label, exact: true }).click();
      }
      await page.getByRole("status", { name: "Загружаем очередь…" }).waitFor();
      const during = await control.boundingBox();
      const noLogo =
        (await page.locator("#main-content .brand-mark").count()) === 0;
      await page
        .getByText("В этой очереди пока нет интервью.", { exact: true })
        .waitFor();
      const after = await control.boundingBox();
      const stable = [during, after].every(
        (rect) =>
          rect &&
          Math.abs(rect.x - before.x) < 1 &&
          Math.abs(rect.y - before.y) < 1,
      );
      report.queueTransitions.push({ width, label, stable, noLogo });
    }
  }
  role = "student";
  await page.setViewportSize({ width: 375, height: 667 });
  await page.goto(baseUrl + "/interviews/python-interview");
  await page
    .getByRole("button", { name: "Показать ответ", exact: true })
    .click();
  await page.waitForTimeout(250);
  report.mobileStudyFits = await page.evaluate(() => {
    const card = document
      .querySelector(".interview-study-card")
      .getBoundingClientRect();
    const ratings = document
      .querySelector(".interview-rating-grid")
      .getBoundingClientRect();
    return (
      card.top >= 76 && ratings.bottom <= innerHeight && ratings.height <= 140
    );
  });
  fs.writeFileSync(outputDir + "/pages.json", JSON.stringify(report, null, 2));
  console.log(
    JSON.stringify(
      {
        ...report,
        pages: report.pages.filter(
          (x) => x.scroll > x.width + 1 || x.low.length || x.clipped.length,
        ),
      },
      null,
      2,
    ),
  );
  await browser.close();
  if (
    !report.mobileStudyFits ||
    report.queueTransitions.some((x) => !x.stable || !x.noLogo) ||
    report.errors.length ||
    report.unhandled.length ||
    report.pages.some(
      (p) =>
        p.statusBackgrounds.length !== new Set(p.statusBackgrounds).size ||
        p.h1Count !== 1 ||
        p.ratingHeight > 140 ||
        p.headerTargets.some((r) => r.width < 44 || r.height < 44) ||
        p.loadingLogoFlashes ||
        p.scroll > p.width + 1 ||
        p.low.length ||
        p.clipped.length,
    ) ||
    !report.favicon.white ||
    !report.favicon.yellow ||
    report.moderationLinks !== 1 ||
    report.mascotNote !== 0 ||
    !report.closedMenuInert ||
    !report.escapeClosed ||
    !report.focusReturned
  )
    process.exitCode = 1;
})();
