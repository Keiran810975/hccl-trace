"use strict";
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const {pathToFileURL} = require("node:url");
const {chromium} = require("playwright");

async function main() {
  const directory = path.resolve(process.argv[2]);
  const report = JSON.parse(fs.readFileSync(path.join(directory, "report.json"), "utf8"));
  const browser = await chromium.launch({headless: true,
    executablePath: process.env.CHROME_PATH || "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"});
  const checks = [];
  try {
    const page = await browser.newPage({viewport: {width: 1500, height: 1100}, reducedMotion: "reduce"});
    const errors = [];
    page.on("pageerror", error => errors.push(error.message));
    await page.goto(pathToFileURL(path.join(directory, "index.html")).href);
    if (!report.candidates.length) {
      assert.match(await page.locator("#layout").innerText(), /未输出候选根因/);
    } else {
      const primaryIndex = Math.max(0, report.candidates.findIndex(root => root.primary));
      assert.equal(await page.locator(`[data-root="${primaryIndex}"]`).getAttribute("aria-pressed"), "true");
      await page.screenshot({path: path.join(directory, "propagation-desktop.png")});
      for (let rootIndex = 0; rootIndex < report.candidates.length; rootIndex++) {
        const root = report.candidates[rootIndex];
        await page.locator(`[data-root="${rootIndex}"]`).click();
        assert.equal(await page.locator("#branch-select option").count(), root.chains.length);
        for (let chainIndex = 0; chainIndex < root.chains.length; chainIndex++) {
          const chain = root.chains[chainIndex];
          await page.locator("#branch-select").selectOption(String(chainIndex));
          const actual = await page.evaluate(() => {
            const root = model.candidates[selected], chain = root.chains[activeBranch];
            return {ids: chain.segments.flatMap(segment => segment.node_ids),
              edges: chain.hops.map(hop => hop.edge_id),
              shown: [...document.querySelectorAll("#flow [data-node]")].map(node => node.dataset.node),
              expectedShown: chain.segments.filter(segment => segment.kind === "task").flatMap(segment => segment.node_ids),
              evidenceRows: document.querySelectorAll("#evidence-rows tr").length,
              hostAnchor: !document.getElementById("host-anchor").hidden,
              complete: chain.path_complete};
          });
          assert.deepEqual(actual.ids, chain.node_ids, "folding lost or invented a node");
          assert.deepEqual(actual.edges, chain.edge_ids, "view changed dependency edges");
          assert.deepEqual(actual.shown, actual.expectedShown);
          assert.equal(actual.evidenceRows, chain.node_ids.length);
          assert.equal(actual.hostAnchor, root.anchor_meaning === "observed_device_anchor_only");
          if (chain.path_complete) assert.equal(actual.shown.at(-1), chain.target_wait_graph_id);
          checks.push({candidate: root.candidate_rank, branch: chainIndex + 1, nodes: actual.ids.length,
            visible: actual.shown.length, complete: actual.complete});
        }
      }
      await page.locator(`[data-root="${primaryIndex}"]`).click();
      const wait = report.nodes[report.candidates[primaryIndex].chains[0]?.target_wait_graph_id];
      if (wait) {
        await page.locator("#rank-filter").selectOption(String(wait.user_rank));
        const ranks = await page.evaluate(() => [...document.getElementById("branch-select").options]
          .map(option => model.nodes[model.candidates[selected].chains[Number(option.value)].target_wait_graph_id].user_rank));
        assert(ranks.every(rank => String(rank) === String(wait.user_rank)));
        await page.locator("#rank-filter").selectOption("all");
        await page.locator("#evidence > summary").click();
        assert(await page.locator("#evidence-rows").isVisible());
        await page.locator("#evidence > summary").click();
        await page.locator("#wait-details > summary").click();
        await page.locator("#wait-rows [data-branch]").last().click();
        assert.equal(await page.locator("#branch-select").inputValue(), String(report.candidates[primaryIndex].chains.length - 1));
        await page.locator("#wait-details > summary").click();
      }
      await page.locator("#search").fill("no-such-task");
      assert(await page.locator("#no-matches").isVisible());
      await page.locator("#search").fill("");
      await page.locator(`[data-root="${primaryIndex}"]`).click();
    }
    for (const width of [1500, 720, 390]) {
      await page.setViewportSize({width, height: 1100});
      await page.evaluate(() => scrollTo(0, 0));
      const layout = await page.evaluate(() => ({width: innerWidth,
        scroll: document.documentElement.scrollWidth,
        zeroSize: [...document.querySelectorAll("#flow .stage-content")].filter(node => node.offsetWidth < 50).length}));
      assert(layout.scroll <= width + 1, `horizontal overflow at ${width}: ${layout.scroll}`);
      assert.equal(layout.zeroSize, 0);
      if (width === 390) await page.screenshot({path: path.join(directory, "propagation-mobile.png")});
    }
    for (const name of ["report.json", "chains.csv", "steps.csv", "chains.md"]) {
      assert(fs.existsSync(path.join(directory, name)), "missing export " + name);
    }
    assert.deepEqual(errors, []);
    const result = {status: "passed", candidates: report.summary.candidate_count,
      branchesChecked: checks.length, viewports: [1500, 720, 390], checks};
    fs.writeFileSync(path.join(directory, "browser-qa.json"), JSON.stringify(result, null, 2) + "\n");
    console.log(JSON.stringify({status: result.status, branchesChecked: checks.length, viewports: result.viewports}));
  } finally {
    await browser.close();
  }
}
main().catch(error => {console.error(error); process.exitCode = 1;});
