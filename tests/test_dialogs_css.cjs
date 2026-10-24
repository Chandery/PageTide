'use strict';
// The shared confirm dialog is centred by the browser's default `margin: auto`; a page with `* { margin: 0 }` (settings.html) removes it.
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const css=fs.readFileSync(path.join(__dirname,'../app/static/dialogs.css'),'utf8');
const rule=css.match(/\.pt-confirm\{([^}]*)\}/)[1];
test('.pt-confirm sets margin:auto so a global margin reset cannot push it into the corner',()=>{
  assert.match(rule,/(^|;)margin:auto(;|$)/);
});
test('the pages that use the dialog load the shared stylesheet, and no page rule overrides its margin',()=>{
  for(const page of ['settings.html','project_creation.html']){
    const html=fs.readFileSync(path.join(__dirname,'../app/static',page),'utf8');
    assert.match(html,/dialogs\.css/,page);
    assert.doesNotMatch(html,/\.pt-confirm\s*\{[^}]*margin/,page);
  }
  const creation=fs.readFileSync(path.join(__dirname,'../app/static/project-creation.css'),'utf8');
  assert.doesNotMatch(creation,/\.(pt-confirm|creation-quit[\w-]*)\s*\{[^}]*margin\s*:\s*0[;}\s]/);
});
