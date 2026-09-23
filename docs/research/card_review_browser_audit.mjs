// Real browser + actual React components; all application API responses are synthetic.
// Usage: node this-file --copilot /path/to/mentoring-copilot
import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { readFile, writeFile, mkdir, unlink } from "node:fs/promises";
import { resolve, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "../..");
const sibling = process.argv[process.argv.indexOf("--copilot") + 1];
const require = createRequire(resolve(sibling, "package.json"));
const { chromium } = require("playwright");
const ts = require("typescript");
const source = await readFile(resolve(root, "frontend/tests/card-automation.test.tsx"), "utf8");
const dataCode = source.slice(source.indexOf("const directionId ="), source.indexOf("beforeEach(() =>"));
const compiled = ts.transpileModule(dataCode, { compilerOptions: { target: ts.ScriptTarget.ES2022 } }).outputText;
const fixtures = new Function(compiled + "\nreturn {clusterDetail, secondCluster, decision};")();
const output = resolve(root, "docs/research/card-review-ui-2026-09-23");
const entry = resolve(root, "frontend/src/card-review-audit.tsx");
await mkdir(output, { recursive: true });
await writeFile(entry, `
import '@mantine/core/styles.css';
import '@mantine/notifications/styles.css';
import './styles.css';
import { createRoot } from 'react-dom/client';
import { createBrowserRouter, RouterProvider } from 'react-router-dom';
import { AppProviders } from './app/providers';
import { AdminCardAutomationClusterDetailPage } from './pages/AdminCardAutomationClusterDetailPage';
const router = createBrowserRouter([{path:'/admin/card-automation/clusters/:clusterId',element:<AdminCardAutomationClusterDetailPage/>}]);
createRoot(document.getElementById('root')!).render(<AppProviders><div style={{padding:16}}><RouterProvider router={router}/></div></AppProviders>);
`, { flag: "wx" });
let browser;
try {
  browser = await chromium.launch({ executablePath: "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", headless: true });
  const context = await browser.newContext();
  const page = await context.newPage();
  const errors = [];
  page.on("pageerror", (error) => { errors.push(error.message); console.error(error.message); });
  const details = new Map([
    [fixtures.clusterDetail.id, structuredClone(fixtures.clusterDetail)],
    [fixtures.secondCluster.id, { ...structuredClone(fixtures.clusterDetail), ...fixtures.secondCluster }],
  ]);
  const writes = [];
  await context.route("**/api/v1/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const headers = { "Access-Control-Allow-Origin": "http://localhost:5173", "Access-Control-Allow-Credentials": "true" };
    if (request.method() === "OPTIONS") return route.fulfill({ status: 204, headers: { ...headers, "Access-Control-Allow-Headers": "*", "Access-Control-Allow-Methods": "GET, POST, OPTIONS" } });
    let data;
    if (url.pathname.endsWith("/review-queue")) data = [...details.values()].filter(d => d.status === "needs_review").map(d => d.id);
    else {
      const match = url.pathname.match(/\/clusters\/([^/]+)(?:\/(create-card|ignore))?$/);
      assert(match && details.has(match[1]), "Unexpected API route: " + url.pathname);
      const card = details.get(match[1]);
      if (request.method() === "POST") {
        writes.push({ id: card.id, action: match[2], payload: request.postDataJSON() });
        card.version++;
        card.status = match[2] === "create-card" ? "card_created" : "ignored";
        card.allowed_actions = [];
        data = { cluster: card, decision_id: fixtures.decision.id, affected_cluster_ids: [card.id] };
      } else data = card;
    }
    await route.fulfill({ json: data, headers });
  });
  await context.route("http://localhost:5173/admin/**", route => route.fulfill({
    contentType: "text/html", body: `<!doctype html><html><head><meta name="viewport" content="width=device-width, initial-scale=1"></head><body><div id="root"></div><script type="module">
import RefreshRuntime from '/@react-refresh';
RefreshRuntime.injectIntoGlobalHook(window);
window.$RefreshReg$ = () => {};
window.$RefreshSig$ = () => (type) => type;
window.__vite_plugin_react_preamble_installed__ = true;
</script><script type="module" src="/@vite/client"></script><script type="module" src="/src/card-review-audit.tsx"></script></body></html>`,
  }));
  await page.goto(`http://localhost:5173/admin/card-automation/clusters/${fixtures.clusterDetail.id}?needs_action_only=true`);
  await page.getByRole("heading", { name: fixtures.clusterDetail.canonical_question, exact: true }).waitFor();
  const layouts = [];
  for (const width of [1440, 1024, 390]) {
    await page.setViewportSize({ width, height: 1000 });
    await page.getByLabel("3. Ответ карточки").scrollIntoViewIfNeeded();
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1);
    const clipped = await page.locator("button .mantine-Button-label").evaluateAll(nodes => nodes.filter(n => n.clientWidth && n.scrollWidth > n.clientWidth + 1).map(n => n.textContent));
    layouts.push({ width, horizontalOverflow: overflow, clippedButtons: clipped });
    await page.screenshot({ path: resolve(output, `review-${width}.png`), fullPage: true });
    assert(!overflow, `Horizontal overflow at ${width}`);
    assert.deepEqual(clipped, [], `Clipped controls at ${width}`);
  }
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.getByLabel("3. Ответ карточки").fill("Проверенный ответ для браузерного сценария.");
  await page.getByRole("button", { name: "Создать карточку", exact: true }).click();
  await page.getByRole("heading", { name: fixtures.secondCluster.canonical_question, exact: true }).waitFor();
  await page.getByText("Осталось в этой очереди: 1 из 2").waitFor();
  await page.getByRole("button", { name: "Отклонить", exact: true }).click();
  await page.getByRole("heading", { name: "Проверка завершена" }).waitFor();
  assert.equal(writes.length, 2);
  assert.equal(writes[0].payload.answer_markdown, "Проверенный ответ для браузерного сценария.");
  assert.deepEqual(errors, []);
  await writeFile(resolve(output, "result.json"), JSON.stringify({ scope: "Real Chrome, synthetic API, actual detail component and theme; without full AppLayout", layouts, mutations: writes.map(({ id, action }) => ({ id, action })), consoleErrors: errors }, null, 2));
  console.log(JSON.stringify({ layouts, mutations: writes.length, errors }));
} finally {
  await browser?.close();
  await unlink(entry);
}
