const vm = require('node:vm');
const fs = require('node:fs');
const assert = require('node:assert/strict');
function element(tag) {
  return {tag,children:[],style:{},dataset:{},append(...items){this.children.push(...items)},
    addEventListener(){},querySelectorAll(){return []}};
}
const nodes={};
const document={addEventListener(){},querySelector:key=>nodes[key]??=element(key),createElement:element};
const context=vm.createContext({document,ResizeObserver:class{observe(){}},
  requestAnimationFrame:()=>1,fetch:async()=>({ok:true,text:async()=>'<section></section>'})});
vm.runInContext(fs.readFileSync('index.html','utf8').split('<script>')[1].split('</script>')[0],context);
(async()=>{
  await vm.runInContext("load({name:'sample.py',size:1})",context);
  const file=nodes.article.children[0];
  assert.equal(file.tag,'details');
  assert.equal(file.children[0].tag,'summary');
  assert.equal(file.children[0].children[1].textContent,'sample.py');
  const owner={matches:()=>true,closest:()=>file};
  const handle={parentElement:owner,setPointerCapture(){}};
  const target={closest:selector=>selector==='summary'?handle:null};
  nodes.main.onpointerdown({button:0,target,pointerId:1,clientX:10,clientY:10});
  nodes.main.onpointermove({pointerId:1,clientX:60,clientY:40});
  assert.equal(file.style.transform,'translate(50px,30px)');
  console.log('File node and class group drag checks passed');
})().catch(error=>{console.error(error);process.exitCode=1});
const child={open:true,style:{transform:'translate(10px,70px)'},dataset:{x:10,y:70}};
context.testParent={querySelectorAll:()=>[child]};
vm.runInContext('collapseChildren(testParent)',context);
assert.equal(child.open,false);
assert.equal(child.style.transform,'');
assert.deepEqual(child.dataset,{});
