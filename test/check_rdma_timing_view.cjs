"use strict";
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const {pathToFileURL} = require("node:url");
const {chromium} = require("playwright");

(async () => {
  const directory = path.resolve(process.argv[2]);
  const report = JSON.parse(fs.readFileSync(path.join(directory, "report.json"), "utf8"),
    (key,value,context)=>typeof value==="number"&&!Number.isSafeInteger(value)?context.source:value);
  const browser = await chromium.launch({headless:true,
    executablePath:process.env.CHROME_PATH || "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"});
  const errors = [], checks = [];
  try {
    const page = await browser.newPage({viewport:{width:1500,height:1000}});
    page.on("pageerror",error=>errors.push(error.message));
    await page.goto(pathToFileURL(path.join(directory,"index.html")).href);
    assert.equal(await page.locator("tbody > tr").count(),report.transfers.length);
    const observed=report.transfers.filter(item=>item.status==="protocol_interval_observed");
    assert.equal(await page.locator("details").count(),observed.length);
    assert.match(await page.locator(".notice").innerText(),/不是纯 RDMA 传输耗时/);
    for (let i=0;i<report.transfers.length;i++) {
      const item=report.transfers[i],row=page.locator("tbody > tr").nth(i);
      if(item.status==="protocol_interval_observed") {
        await row.locator("summary").click();
        assert.equal(await row.locator("li").count(),item.evidence_node_ids.length);
        const text=await row.innerText();
        for(const id of item.evidence_node_ids)assert(text.includes(id));
        for(const id of item.evidence_edge_ids)assert(text.includes(id));
        assert(text.includes(String(item.protocol_start_ns)));
        assert(text.includes(String(item.protocol_stop_ns)));
        await row.locator("summary").click();
      }
    }
    for(const width of [1500,720,390]) {
      await page.setViewportSize({width,height:1000});
      await page.evaluate(()=>scrollTo(0,0));
      const size=await page.evaluate(()=>({width:innerWidth,scroll:document.documentElement.scrollWidth,
        flow:document.querySelectorAll(".flow li").length}));
      assert(size.scroll<=width+1,"page overflows horizontally");
      if(observed.length)assert(size.flow>0);
      if(width===1500||width===390)await page.screenshot({path:path.join(directory,`preview-${width}.png`)});
      checks.push(size);
    }
    assert.deepEqual(errors,[]);
    const result={status:"passed",transfers:report.transfers.length,pathsChecked:observed.length,viewports:checks};
    fs.writeFileSync(path.join(directory,"browser-qa.json"),JSON.stringify(result,null,2)+"\n");
    console.log(JSON.stringify(result));
  } finally {await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
