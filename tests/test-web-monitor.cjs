const {test} = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const source = fs.readFileSync('web/app.js','utf8').split("document.addEventListener('input'")[0];
function context() {const ctx={window:{}};vm.createContext(ctx);vm.runInContext(source,ctx);return ctx;}

test('identical feed failures are grouped and escaped, with all affected symbols retained',()=>{
  const ctx=context();
  const html=ctx.marketErrors({'510300.SH':'网络<异常>','600519.SH':'网络<异常>','159915.SZ':'历史不足'});
  assert.equal((html.match(/网络&lt;异常&gt;/g)||[]).length,1);
  assert.match(html,/3 只标的/);
  assert.match(html,/510300.SH、600519.SH/);
  assert.match(html,/历史不足/);
  assert.equal(ctx.marketErrors({}),'');
});

test('per-symbol shortcut opens rules scoped to exactly that symbol; editing keeps saved scope',()=>{
  const ctx=context();
  vm.runInContext(`state.watch=[{symbol:'510300.SH',name:'沪深300ETF'},{symbol:'600519.SH',name:'贵州茅台'}];state.symbol='600519.SH';state.ruleSymbol='600519.SH';`,ctx);
  assert.match(ctx.monitorShortcut(),/data-manage-rules="600519.SH"/);
  const fresh=ctx.scopeEditor();
  assert.match(fresh,/value="selected" selected/);
  assert.match(fresh,/value="600519.SH" checked/);
  assert.doesNotMatch(fresh,/value="510300.SH" checked/);
  const edited=ctx.scopeEditor({symbols:['510300.SH'],enabled:false});
  assert.match(edited,/value="510300.SH" checked/);
  assert.doesNotMatch(edited,/value="600519.SH" checked/);
});
