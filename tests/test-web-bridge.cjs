const {test} = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const source = fs.readFileSync('web/app.js','utf8').split('\nconst send =')[0];

test('phone requests use only native transport and preserve method/body', async () => {
  const context = {window:{},setTimeout,clearTimeout};
  context.window.GuanlanNative = {request(id,method,path,body) {
    assert.equal(method,'POST'); assert.equal(path,'/api/rules'); assert.equal(body,'{"name":"规则"}');
    queueMicrotask(()=>context.window.guanlanResponse(id,JSON.stringify({status:200,body:{id:7}})));
  }};
  context.fetch = ()=>{throw Error('Phone must not access a desktop server');};
  vm.runInNewContext(source,context);
  const result = await context.api('/rules',{method:'POST',body:'{"name":"规则"}'});
  assert.equal(result.id,7);
});
test('native validation errors are shown instead of treated as successful saves', async () => {
  const context = {window:{},setTimeout,clearTimeout};
  context.window.GuanlanNative = {request(id) {queueMicrotask(()=>context.window.guanlanResponse(id,JSON.stringify({status:400,body:{detail:'规则无效'}})));}};
  vm.runInNewContext(source,context);
  await assert.rejects(context.api('/rules',{method:'POST'}),/规则无效/);
});
test('desktop continues to use same-origin HTTP', async () => {
  const context = {window:{},setTimeout,clearTimeout,fetch:async(path)=>{
    assert.equal(path,'/api/status');return {status:200,ok:true,json:async()=>({runtime:'desktop'})};
  }};
  vm.runInNewContext(source,context);
  assert.equal((await context.api('/status')).runtime,'desktop');
});
