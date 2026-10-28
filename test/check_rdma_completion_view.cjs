"use strict";
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const {pathToFileURL} = require("node:url");
const {chromium} = require("playwright");

(async () => {
  const directory = path.resolve(process.argv[2]);
  const report = JSON.parse(fs.readFileSync(path.join(directory, "report.json"), "utf8"));
  const browser = await chromium.launch({headless:true,
    executablePath:process.env.CHROME_PATH || "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"});
  try {
    const page = await browser.newPage();
    const errors = [], checks = [];
    page.on("pageerror", error => errors.push(error.message));
    await page.goto(pathToFileURL(path.join(directory, "index.html")).href);
    assert.equal(await page.locator("tbody > tr").count(), report.operations.length);
    assert.match(await page.locator(".status").innerText(), /未具备/);
    for (const width of [1500, 720, 390]) {
      await page.setViewportSize({width, height:1000});
      const size = await page.evaluate(() => ({width:innerWidth, scroll:document.documentElement.scrollWidth}));
      assert(size.scroll <= width + 1, "page overflows horizontally");
      checks.push(size);
    }
    for (const link of await page.locator("a").evaluateAll(nodes => nodes.map(node => node.href))) {
      assert.equal(fs.existsSync(require("node:url").fileURLToPath(link)), true, "broken report link");
    }
    assert.deepEqual(errors, []);
    const result = {status:"passed", rows:report.operations.length, viewports:checks};
    fs.writeFileSync(path.join(directory, "browser-qa.json"), JSON.stringify(result, null, 2) + "\n");
    console.log(JSON.stringify(result));
  } finally { await browser.close(); }
})().catch(error => {console.error(error); process.exitCode = 1;});
