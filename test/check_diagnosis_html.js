// Artifact/interaction smoke check, not a substitute for rendered browser QA.
// Usage: node test/check_diagnosis_html.js < execution.html
'use strict';
const fs = require('fs'), vm = require('vm'), assert = require('assert');
const html = fs.readFileSync(0, 'utf8');
const scripts = [...html.matchAll(/<script>([\s\S]*?)<\/script>/g)];
assert.strictEqual(scripts.length, 1);
const ids = new Set([...html.matchAll(/id="([^"]+)"/g)].map(m => m[1]));
const context2d = new Proxy({}, {get: (_, key) => key === 'measureText' ? () => ({width: 10}) : () => {}, set: () => true});
class Element {
  constructor(tag = '') {
    this.tag = tag; this.children = []; this.value = ''; this.checked = false;
    this.style = {setProperty() {}}; this.clientWidth = 1200; this.clientHeight = 700;
    this.handlers = {}; this.textContent = ''; this.hidden = false;
  }
  get options() { return this.children; }
  append(...children) { this.children.push(...children); }
  replaceChildren(...children) { this.children = children; }
  addEventListener(name, fn) { this.handlers[name] = fn; }
  getContext() { return context2d; }
  getBoundingClientRect() { return {left: 0, top: 0, width: this.clientWidth, height: this.clientHeight}; }
  focus() {}
}
const elements = new Map([...ids].map(id => [id, new Element(id)]));
const frames = [];
const sandbox = {
  document: {
    getElementById(id) { assert(elements.has(id), `missing DOM element: ${id}`); return elements.get(id); },
    createElement(tag) { return new Element(tag); }
  },
  window: {innerWidth: 1600, innerHeight: 1000, devicePixelRatio: 1, addEventListener() {}},
  requestAnimationFrame(fn) { frames.push(fn); }, location: {hash: ''}, console
};
vm.createContext(sandbox);
vm.runInContext(scripts[0][1], sandbox, {timeout: 15000});
while (frames.length) frames.shift()();
vm.runInContext(`
if (!model.initialOperation || controls.operation.value !== model.initialOperation) throw Error('operation focus missing');
if (model.graphView === 'resource' && document.getElementById('boundaries').checked) throw Error('control boundaries not hidden');
if (model.edges.some(e => !e.id)) throw Error('edge evidence ID missing');
if (model.graphView === 'waits') {
  if (!model.waits.length || model.waits.some(w => !w.classification)) throw Error('wait analysis missing');
  const w = model.waits.find(w => w.evidence_path_edge_ids) || model.waits[0];
  selectContext(w.wait_graph_id);
  if (selectedId !== w.wait_graph_id) throw Error('wait selection failed');
  const path = new Set((w.evidence_path_edge_ids || '').split(';').filter(Boolean));
  if ([...path].some(id => !selectedEdges().some(e => e.id === id))) throw Error('evidence path not highlighted');
}
const candidate = (model.diagnosis?.candidates || []).find(c => nodeById.has(c.graph_id));
if (candidate) { selectContext(candidate.graph_id); if (selectedId !== candidate.graph_id) throw Error('candidate selection failed'); }
controls.phase.value = model.nodes.find(n => n.phase)?.phase || '';
renderWaits(); renderCandidates(); fit();
`, sandbox, {timeout: 15000});
while (frames.length) frames.shift()();
console.log('HTML_INTERACTION_SMOKE_PASS');
