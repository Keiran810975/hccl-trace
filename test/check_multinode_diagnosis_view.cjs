"use strict";
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const {pathToFileURL} = require("node:url");
const {chromium} = require("playwright");

(async () => {
  const directories = process.argv.slice(2).map(p => path.resolve(p));
  const browser = await chromium.launch({headless:true,
    executablePath:process.env.CHROME_PATH || "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"});
  const checks = [];
  try {
    for (const directory of directories) {
      const result = JSON.parse(fs.readFileSync(path.join(directory, "pipeline_result.json"), "utf8"));
      for (const width of [1500, 720, 390]) {
        const page = await browser.newPage({viewport:{width, height:1000}});
        const errors = [];
        page.on("pageerror", error => errors.push(error.message));
        await page.goto(pathToFileURL(path.join(directory, "execution.html")).href);
        const state = await page.evaluate(() => ({aligned:!!model.clockAlignment,
          protocols:model.nodes.filter(n=>n.nodeKind==="protocol").length,
          operations:model.nodes.filter(n=>n.nodeKind==="operation").length,
          edges:model.edges.length, label:model.clockLabel}));
        assert.equal(state.aligned, result.clock_alignment_available);
        if (state.aligned) assert.match(state.label, /Estimated aligned/);
        if (state.protocols) {
          await page.evaluate(() => selectContext(model.nodes.find(n=>n.nodeKind==="protocol").id));
          assert.equal(await page.locator("#sideTitle").innerText(), "Cross-node protocol interval");
          assert.match(await page.locator("#details").innerText(), /not pure network/);
          const tasks = page.locator("#details button.dep");
          assert(await tasks.count() >= 4);
          await tasks.first().click();
          assert.match(await page.locator("#sideTitle").innerText(), /Task/);
          // Exercise candidate controls with temporary browser-only fixture state.
          await page.evaluate(() => {
            const n=model.nodes.find(n=>n.nodeKind==="protocol");
            window.savedProtocol=structuredClone(n.protocol);
            n.protocol.is_slow=true; fit();renderCandidates();
          });
          assert.match(await page.locator("#candidateList").innerText(), /physical cause unknown/);
          await page.locator("#candidateList button.dep").last().click();
          assert.equal(await page.locator("#sideTitle").innerText(), "Cross-node protocol interval");
          await page.evaluate(() => {
            model.nodes.find(n=>n.nodeKind==="protocol").protocol=window.savedProtocol;
            delete window.savedProtocol;renderCandidates();
          });
        }
        await page.waitForTimeout(100);
        const canvas = await page.evaluate(() => {
          const c=document.getElementById("trace"),data=c.getContext("2d").getImageData(0,0,c.width,c.height).data;
          let nonwhite=0; for(let i=0;i<data.length;i+=4)if(data[i]<240||data[i+1]<240||data[i+2]<240)nonwhite++;
          return {width:c.width,height:c.height,nonwhite,overflow:document.documentElement.scrollWidth>innerWidth+1};
        });
        assert(canvas.width>0 && canvas.height>0 && canvas.nonwhite>100);
        assert.equal(canvas.overflow, false);
        assert.deepEqual(errors, []);
        if(width===1500||width===390)await page.screenshot({path:path.join(directory, `multinode-${width}.png`)});
        checks.push({directory,width,...state,...canvas});
        await page.close();
      }
      const page = await browser.newPage({viewport:{width:1200,height:900}});
      await page.goto(pathToFileURL(path.join(directory,"cross_node/index.html")).href);
      const report = JSON.parse(fs.readFileSync(path.join(directory,"cross_node/report.json"),"utf8"));
      assert.equal(await page.locator("tbody > tr").count(),report.segments.length);
      await page.close();
    }
    const target = path.join(directories[0], "multinode-browser-qa.json");
    fs.writeFileSync(target, JSON.stringify({status:"passed",checks}, null, 2)+"\n");
    console.log(JSON.stringify({status:"passed",viewports:checks.length}));
  } finally { await browser.close(); }
})().catch(error=>{console.error(error);process.exitCode=1;});
