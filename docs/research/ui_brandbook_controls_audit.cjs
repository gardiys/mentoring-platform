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
const fs = require("fs");
(async () => {
  const browser = await chromium.launch({
    executablePath: process.env.CHROME_BIN || undefined,
    headless: true,
  });
  const page = await browser.newPage({
    viewport: { width: 1440, height: 1000 },
  });
  await page.route("**/api/v1/**", (r) =>
    r.fulfill({
      status: 401,
      contentType: "application/json",
      body: JSON.stringify({
        detail: { code: "unauthorized", message: "Unauthorized" },
      }),
    }),
  );
  await page.goto(baseUrl + "/dev-login");
  await page.getByText("Development-вход").waitFor();
  await page.evaluate(async () => {
    const { createElement: h } = (
      await import("/node_modules/.vite/deps/react.js")
    ).default;
    const { createRoot } = (
      await import("/node_modules/.vite/deps/react-dom_client.js")
    ).default;
    const m = await import("/node_modules/.vite/deps/@mantine_core.js");
    const { brandTheme, brandCssVariables } = await import("/src/app/theme.ts");
    document.getElementById("root").style.display = "none";
    const mount = document.createElement("div");
    document.body.append(mount);
    const root = createRoot(mount);
    const colors = [
      "brandBlue",
      "blue",
      "brandYellow",
      "brandAi",
      "red",
      "green",
      "gray",
      "brandNavy",
      "cyan",
      "orange",
      "teal",
    ];
    const variants = ["filled", "light", "outline", "subtle", "default"];
    const content = h(
      m.Stack,
      { p: 32 },
      ...variants.map((variant) =>
        h(
          m.Group,
          { key: variant },
          ...colors.map((color) =>
            h(
              m.Button,
              {
                key: color,
                color,
                variant,
                "data-audit": variant + "-" + color,
              },
              variant + " " + color,
            ),
          ),
        ),
      ),
    );
    window.preview = (scheme) =>
      root.render(
        h(
          m.MantineProvider,
          {
            theme: brandTheme,
            cssVariablesResolver: brandCssVariables,
            forceColorScheme: scheme,
          },
          content,
        ),
      );
    window.preview("dark");
  });
  const failures = [];
  let checked = 0;
  for (const theme of ["dark"]) {
    await page.evaluate((s) => window.preview(s), theme);
    await page.waitForTimeout(200);
    for (const button of await page.locator("[data-audit]").all()) {
      for (const state of ["normal", "hover", "pressed", "disabled"]) {
        await button.evaluate((e, disabled) => {
          e.disabled = disabled;
        }, state === "disabled");
        if (state === "normal" || state === "disabled")
          await page.mouse.move(0, 0);
        else await button.hover();
        if (state === "pressed") await page.mouse.down();
        await page.waitForTimeout(80);
        const result = await button.evaluate((e) => {
          const c = document.createElement("canvas");
          c.width = c.height = 1;
          const ctx = c.getContext("2d", { willReadFrequently: true });
          function rgb(s) {
            ctx.clearRect(0, 0, 1, 1);
            ctx.fillStyle = s;
            ctx.fillRect(0, 0, 1, 1);
            return [...ctx.getImageData(0, 0, 1, 1).data];
          }
          function bg(e) {
            const a = rgb(getComputedStyle(e).backgroundColor);
            if (a[3] === 255) return a;
            const b = e.parentElement
              ? bg(e.parentElement)
              : [255, 255, 255, 255];
            return a
              .slice(0, 3)
              .map((x, i) => (x * a[3]) / 255 + b[i] * (1 - a[3] / 255));
          }
          function l(c) {
            return c
              .slice(0, 3)
              .map((x) => x / 255)
              .map((x) =>
                x <= 0.04045 ? x / 12.92 : ((x + 0.055) / 1.055) ** 2.4,
              )
              .reduce((s, x, i) => s + x * [0.2126, 0.7152, 0.0722][i], 0);
          }
          const s = getComputedStyle(e),
            a = l(rgb(s.color)),
            b = l(bg(e));
          return {
            label: e.dataset.audit,
            ratio: (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05),
            border: s.borderTopStyle,
            width: s.borderTopWidth,
          };
        });
        checked++;
        if (
          result.ratio < 4.5 ||
          (result.label.startsWith("outline") &&
            (result.border !== "solid" || result.width !== "1px"))
        )
          failures.push({ theme, state, ...result });
        if (state === "pressed") await page.mouse.up();
      }
    }
  }
  fs.writeFileSync(
    outputDir + "/controls.json",
    JSON.stringify({ checked, failures }, null, 2),
  );
  console.log(JSON.stringify({ checked, failures }, null, 2));
  await browser.close();
  if (failures.length) process.exitCode = 1;
})();
