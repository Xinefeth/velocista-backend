// EN-38: ejecuta cada caso FUN desde Swagger UI (Try it out -> Execute) y guarda una captura.
// Uso: node capture.cjs <carpeta-frontend con @playwright/test> <url-backend> plan.json <carpeta-salida>
const path = require('path');
const fs = require('fs');
const [front, base, planFile, outDir] = process.argv.slice(2);
const { chromium } = require(path.join(front, 'node_modules', '@playwright', 'test'));

const CSS = `
  .swagger-ui textarea.body-param__text { max-height: 220px !important; height: 220px !important; }
  .swagger-ui .responses-inner .highlight-code pre,
  .swagger-ui .responses-inner .microlight { max-height: 360px !important; overflow: hidden !important; }
  .swagger-ui .curl-command, .swagger-ui .request-url, .swagger-ui .responses-table:not(.live-responses-table) { display: none !important; }
`;

(async () => {
  const plan = JSON.parse(fs.readFileSync(planFile, 'utf8'));
  fs.mkdirSync(outDir, { recursive: true });
  const browser = await chromium.launch();
  const results = [];
  for (const c of plan) {
    const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
    await page.goto(`${base}/docs#/${c.tag}/${c.operationId}`);
    await page.addStyleTag({ content: CSS });
    const block = page.locator(`#operations-${c.tag}-${c.operationId}`);
    await block.waitFor();
    if (!(await block.locator('.opblock-body').count())) await block.locator('.opblock-summary').first().click();
    await block.getByRole('button', { name: 'Try it out' }).click();
    for (const [name, value] of Object.entries(c.params)) {
      await block.locator(`tr[data-param-name="${name}"] input`).fill(String(value));
    }
    if (c.body !== null) await block.locator('textarea.body-param__text').fill(c.body);
    await block.locator('button.execute').click();
    const status = block.locator('.live-responses-table tbody .response-col_status').first();
    await status.waitFor({ timeout: 60000 });
    const got = (await status.innerText()).trim().split(/\s/)[0];
    // título del caso encima del bloque, para que la captura se explique sola
    await block.evaluate((el, label) => {
      const tag = document.createElement('div');
      tag.textContent = label;
      tag.style.cssText = 'font:600 16px sans-serif;padding:8px 12px;background:#1b1b1b;color:#fff';
      el.prepend(tag);
    }, `${c.id} · ${c.title} · esperado ${c.status} · obtenido ${got}`);
    await block.screenshot({ path: path.join(outDir, `${c.id}.png`) });
    results.push({ id: c.id, expected: c.status, got: Number(got) });
    console.log(c.id, c.status, got, Number(got) === c.status ? 'OK' : 'DIFERENTE');
    await page.close();
  }
  await browser.close();
  fs.writeFileSync(path.join(outDir, '..', 'swagger-capture-results.json'), JSON.stringify(results, null, 1));
})().catch((e) => { console.error(e); process.exit(1); });
