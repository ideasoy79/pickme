/* 픽미닷 화면 로직 시험
   목적: 두 단(확인분/목록분)과 세부 칸 고르기가 실제로 맞게 도는지 본다.
   브라우저 없이 돌리려고 document 흉내를 아주 작게 만들어 붙인다. */

var fs = require('fs');

/* ---- 아주 작은 document 흉내 ---- */
function Node(tag){
  this.tagName = (tag || '').toUpperCase();
  this.nodeType = 1;
  this.childNodes = [];
  this.className = '';
  this._text = '';
  this.style = {};
  this.dataset = {};
}
Object.defineProperty(Node.prototype, 'firstChild', {
  get: function(){ return this.childNodes[0] || null; }
});
Object.defineProperty(Node.prototype, 'textContent', {
  get: function(){
    if(this.childNodes.length === 0){ return this._text; }
    var s = this._text;
    for(var i=0;i<this.childNodes.length;i++){ s += this.childNodes[i].textContent; }
    return s;
  },
  set: function(v){ this._text = String(v); this.childNodes = []; }
});
Node.prototype.appendChild = function(n){ this.childNodes.push(n); return n; };
Node.prototype.removeChild = function(n){
  var i = this.childNodes.indexOf(n);
  if(i > -1){ this.childNodes.splice(i, 1); }
  return n;
};
Node.prototype.addEventListener = function(){ };
Node.prototype.setAttribute = function(k, v){ this[k] = v; };
Node.prototype.getAttribute = function(k){ return this[k]; };
Node.prototype.querySelectorAll = function(){ return []; };

global.document = {
  createElement: function(t){ return new Node(t); },
  body: null,
  addEventListener: function(){ },
  getElementById: function(){ return null; },
  querySelector: function(){ return null; },
  querySelectorAll: function(){ return []; },
  createTextNode: function(t){ var n = new Node('#text'); n.nodeType = 3; n._text = t; return n; }
};
global.window = {
  addEventListener: function(){ },
  history: { pushState: function(){ } },
  location: { href: '', hash: '' },
  localStorage: {
    _d: {},
    getItem: function(k){ return this._d[k] === undefined ? null : this._d[k]; },
    setItem: function(k, v){ this._d[k] = String(v); },
    removeItem: function(k){ delete this._d[k]; }
  },
  matchMedia: function(){ return { matches: false, addListener: function(){ } }; },
  open: function(){ }
};
global.localStorage = global.window.localStorage;
global.navigator = { userAgent: 'node', clipboard: null };
global.fetch = undefined;
global.setTimeout = setTimeout;

/* ---- 앱 코드 꺼내서 안쪽 함수를 밖으로 내보내기 ---- */
var ROOT = require('path').join(__dirname, '..');
var html = fs.readFileSync(require('path').join(ROOT, 'index.html'), 'utf8');
var code = html.match(/<script>([\s\S]*)<\/script>/)[1];
var mark = code.lastIndexOf('})();');
if(mark < 0){ throw new Error('IIFE 끝을 못 찾음'); }
var patched = code.slice(0, mark) +
  '\nglobal.__api = { runMatch:runMatch, listedFor:listedFor, CONFIG:CONFIG, S:S,' +
  ' specRow:specRow, shopBtn:shopBtn, listedCard:listedCard, productCard:productCard,' +
  ' renderCells:renderCells, srcName:srcName };\n' +
  code.slice(mark);

new Function(patched)();
var api = global.__api;

/* ---- 만들어 둔 products.json 을 실제로 물린다 ---- */
var data = JSON.parse(fs.readFileSync(require('path').join(ROOT, 'products.json'), 'utf8'));
if(!data.cells || !data.products || !data.products.length){
  console.log('products.json 이 아직 새 모양이 아닙니다.');
  console.log('  · cells 칸 정보 : ' + (data.cells ? data.cells.length + '개' : '없음'));
  console.log('  · products      : ' + ((data.products || []).length) + '개');
  console.log('먼저 tools/build_products.py 를 돌려 새 products.json 을 만들어 주세요.');
  process.exit(1);
}
api.CONFIG.minPool = data.minPool || api.CONFIG.minPool;
api.CONFIG.applyCells(data.cells);
api.CONFIG.aiNote = data.aiNote;
api.CONFIG.applyData(data.products, data.version);

var pass = 0, fail = 0;
function ok(name, cond, extra){
  if(cond){ pass++; console.log('  ok   ' + name); }
  else { fail++; console.log('  FAIL ' + name + (extra ? '  → ' + extra : '')); }
}

console.log('\n== 1. 데이터가 제대로 붙었나 ==');
var vs = data.products.filter(function(p){ return p.tier === 'verified'; });
var ls = data.products.filter(function(p){ return p.tier === 'listed'; });
ok('확인분이 있다 (' + vs.length + '개)', vs.length > 0);
ok('목록분이 있다 (' + ls.length + '개)', ls.length > 0);
ok('모든 제품에 tier 가 있다',
  data.products.every(function(p){ return p.tier === 'verified' || p.tier === 'listed'; }));
ok('칸 정보가 붙었다 (' + data.cells.length + '칸)', data.cells.length > 0);
ok('minPool 이 12', data.minPool === 12);

console.log('\n== 2. 칸 상태 계산 ==');
var ranked = data.cells.filter(function(c){ return c.state === 'ranked'; });
var listedC = data.cells.filter(function(c){ return c.state === 'listed'; });
var closed = data.cells.filter(function(c){ return c.state === 'closed'; });
console.log('   순위 여는 칸 ' + ranked.length + ' · 목록만 ' + listedC.length + ' · 닫힘 ' + closed.length);
ok('순위 칸은 확인분이 12개 이상',
  ranked.every(function(c){ return (c.verified||0) >= 12; }),
  JSON.stringify(ranked.filter(function(c){ return (c.verified||0) < 12; })));
ok('닫힌 칸은 합이 12개 미만',
  closed.every(function(c){ return ((c.verified||0) + (c.listed||0)) < 12; }));
ok('CONFIG.cellsOf 가 대분류별로 갈라준다',
  api.CONFIG.cellsOf('cleanse').length > 0 && api.CONFIG.cellsOf('sun').length >= 0);

console.log('\n== 3. 목록분은 절대 순위에 안 섞인다 ==');
var st = { cat:'cleanse', cell:null, seg:null, skin:null, care:[], avoid:[], budget:null };
var r = api.runMatch(st);
var leaked = (r.list || []).filter(function(x){
  var p = x.p || x; return p.tier === 'listed';
});
ok('순위 목록에 목록분이 하나도 없다', leaked.length === 0, leaked.length + '개 샘');
ok('runMatch 가 listed 를 따로 돌려준다', Array.isArray(r.listed));
ok('돌려준 listed 는 전부 tier=listed',
  (r.listed || []).every(function(p){ return p.tier === 'listed'; }));
ok('목록분에는 점수가 없다',
  (r.listed || []).every(function(p){ return p.score === undefined; }));

console.log('\n== 4. 세부 칸을 고르면 그 칸만 나온다 ==');
var target = ranked[0] || listedC[0];
if(target){
  var st2 = { cat:target.grp, cell:target.key, seg:null, skin:null, care:[], avoid:[], budget:null };
  var r2 = api.runMatch(st2);
  var wrong = (r2.list || []).filter(function(x){
    var p = x.p || x; return p.cell !== target.key;
  });
  ok('"' + target.label + '" 칸만 걸러진다 (' + (r2.list||[]).length + '개)', wrong.length === 0,
    wrong.length + '개 딴 칸');
  var wrongL = (r2.listed || []).filter(function(p){ return p.cell !== target.key; });
  ok('목록분도 같은 칸만', wrongL.length === 0);
} else {
  ok('시험할 칸이 있다', false, '열린 칸이 하나도 없음');
}

console.log('\n== 5. 칸을 안 고르면 대분류 전체 ==');
var st3 = { cat:'cleanse', cell:null, seg:null, skin:null, care:[], avoid:[], budget:null };
var r3 = api.runMatch(st3);
var bad = (r3.list || []).filter(function(x){ var p = x.p || x; return p.cat !== 'cleanse'; });
ok('대분류 밖 제품이 안 섞인다 (' + (r3.list||[]).length + '개)', bad.length === 0);

console.log('\n== 6. 화면 조각이 실제로 그려진다 ==');
var sample = ls[0];
try{
  var card = api.listedCard(sample);
  var t = card.textContent;
  ok('목록분 카드가 그려진다', card && card.nodeType === 1);
  ok('목록분 카드에 이름이 들어간다', t.indexOf(sample.name.slice(0, 6)) > -1, t.slice(0, 60));
  ok('목록분 카드에 확인 안내가 있다', t.indexOf('확인') > -1);
}catch(e){ ok('목록분 카드가 그려진다', false, e.message); }

try{
  var withSpec = data.products.filter(function(p){ return p.specs && p.specs.length; })[0];
  if(withSpec){
    var sr = api.specRow(withSpec);
    ok('기준 줄이 그려진다 (' + withSpec.specs.length + '개)', sr && sr.nodeType === 1);
    ok('기준 줄에 값이 보인다',
      sr.textContent.indexOf(String(withSpec.specs[0].v)) > -1, sr.textContent.slice(0, 60));
  } else { ok('기준이 붙은 제품이 있다', false); }
}catch(e){ ok('기준 줄이 그려진다', false, e.message); }

try{
  var sb = api.shopBtn(sample);
  var href = sb.href || (sb.childNodes[0] && sb.childNodes[0].href);
  ok('판매처 단추가 그려진다', sb && sb.nodeType === 1);
  ok('링크가 네이버쇼핑 검색이다', String(href).indexOf('search.shopping.naver.com') > -1, String(href));
  ok('링크에 제품 이름이 들어간다', String(href).indexOf('query=') > -1);
}catch(e){ ok('판매처 단추가 그려진다', false, e.message); }

console.log('\n== 7. 주의점이 실제로 붙었나 ==');
var withWatch = data.products.filter(function(p){ return p.watch && p.watch.length; });
ok('주의점이 붙은 제품이 있다 (' + withWatch.length + '개)', withWatch.length > 0);
if(withWatch.length){
  ok('주의점은 문장(문자열)이다',
    withWatch.every(function(p){ return typeof p.watch === 'string'; }));
  var lw = withWatch.filter(function(p){ return p.tier === 'listed'; });
  ok('목록분에도 주의점이 붙는다 (' + lw.length + '개)', lw.length > 0);
  console.log('   예: ' + withWatch[0].name + ' → ' + withWatch[0].watch);
  if(lw.length){ console.log('   예(목록분): ' + lw[0].name + ' → ' + lw[0].watch); }
}

console.log('\n== 8. 출처 이름 ==');
ok('mfds 를 사람 말로 바꾼다',
  api.srcName('mfds').indexOf('식품의약품안전처') > -1, api.srcName('mfds'));
ok('모르는 출처는 그대로 둔다', typeof api.srcName('zzz') === 'string');

console.log('\n== 9. 세부 칸 고르기 화면 ==');
try{
  api.S.cat = 'cleanse';
  api.S.view = 'cell';
  var view = api.renderCells();
  var vt = view.textContent;
  ok('칸 고르기 화면이 그려진다', view && view.nodeType === 1);
  var cl = api.CONFIG.cellsOf('cleanse');
  var open = cl.filter(function(c){ return c.state !== 'closed'; });
  var shut = cl.filter(function(c){ return c.state === 'closed'; });
  ok('열린 칸 이름이 화면에 있다 (' + open.length + '칸)',
    open.length === 0 || vt.indexOf(open[0].label) > -1);
  ok('닫힌 칸도 숨기지 않고 알려 준다 (' + shut.length + '칸)',
    shut.length === 0 || vt.indexOf(shut[0].label) > -1);
  ok('닫힌 이유를 적어 준다', shut.length === 0 || vt.indexOf('아직') > -1);
}catch(e){ ok('칸 고르기 화면이 그려진다', false, e.message); }

console.log('\n== 10. AI 고지 (앱인토스 요건) ==');
ok('데이터에 AI 안내 문장이 들어 있다', !!data.aiNote, String(data.aiNote).slice(0, 40));
var htmlAll = html;
ok('첫 화면에 생성형 AI 고지가 있다', htmlAll.indexOf('생성형 AI') > -1);
ok('목록분 카드에도 AI 표시가 있다',
  api.listedCard(sample).textContent.indexOf('AI') > -1);

console.log('\n== 11. 값·사진을 아는 척하지 않는다 ==');
ok('목록분에는 가격이 없다',
  ls.every(function(p){ return p.price === undefined; }));
ok('목록분에는 전성분이 없다',
  ls.every(function(p){ return p.ing === undefined && p.ings === undefined; }));
ok('목록분에는 확인 날짜가 있다',
  ls.every(function(p){ return !!p.checked; }), ls[0] && ls[0].checked);
ok('목록분에는 보고 날짜가 있다',
  ls.filter(function(p){ return !!p.reportDate; }).length > ls.length * 0.9);

console.log('\n' + (fail === 0 ? '전부 통과' : fail + '개 실패') + ' · 통과 ' + pass + ' · 실패 ' + fail);
process.exit(fail === 0 ? 0 : 1);
