// Real-browser QA for the self-contained retained dependency excerpt.
'use strict';
const assert = require('assert');
const {pathToFileURL} = require('url');
const {chromium} = require('playwright');

(async () => {
  const browser = await chromium.launch({headless: true, executablePath: process.env.CHROME_PATH || chromium.executablePath()});
  try {
    const page = await browser.newPage({viewport: {width: 1700, height: 1050}});
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.goto(pathToFileURL(process.argv[2]).href, {waitUntil: 'load', timeout: 90000});
    await page.waitForTimeout(500);
    const result = await page.evaluate(() => {
      const edge = model.edges.find(e => e.kind.includes('notify_sync') && nodeById.get(e.src)?.rank !== nodeById.get(e.dst)?.rank);
      if (!edge) throw Error('No cross-rank synchronization in retained artifact');
      selectContext(edge.dst);
      const selected = selectedEdges().some(e => e.id === edge.id);
      return {nodes: model.nodes.length, edges: model.edges.length, crossRankEdge: edge.id,
              selectedDependencyVisible: selected, locations: model.caseInfo.injection_locations,
              title: document.title, bodyWidth: document.body.scrollWidth};
    });
    await page.waitForTimeout(100);
    result.coloredPixels = await page.evaluate(() => {
      const data = ctx.getImageData(0, 0, canvas.width, canvas.height).data;
      let count = 0;
      for (let i = 0; i < data.length; i += 4) {
        if (data[i + 3] && Math.max(data[i], data[i + 1], data[i + 2]) - Math.min(data[i], data[i + 1], data[i + 2]) > 25) count++;
      }
      return count;
    });
    assert.strictEqual(errors.length, 0, errors.join('\n'));
    assert(result.selectedDependencyVisible && result.coloredPixels > 100);
    if (process.argv[3]) await page.screenshot({path: process.argv[3]});
    console.log(JSON.stringify(result));
  } finally {
    await browser.close();
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
