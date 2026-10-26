// A CNKI query of several words that finds nothing is tried again with fewer words, never walked through empty tabs.
const test = require('node:test');
const assert = require('node:assert');
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const driver = fs.readFileSync(path.join(__dirname, '..', 'src-tauri', 'src', 'cnki_driver.js'), 'utf8');
const slice = (from, to) => driver.slice(driver.indexOf(from), driver.indexOf(to, driver.indexOf(from)));

test('a long query drops its last word, down to one word and at most three times', () => {
  const context = vm.createContext({});
  vm.runInContext(slice('const MAX_RELAX', '\n\n') + ';globalThis.shorter = shorter;', context);
  assert.equal(context.shorter('国际中文教育 语法教学法 课堂设计 研究', {}), '国际中文教育 语法教学法 课堂设计');
  assert.equal(context.shorter('汉语语法教学  任务型教学', {relaxes: 1}), '汉语语法教学');
  assert.equal(context.shorter('语法教学', {}), null);                       // one word: nothing to drop
  assert.equal(context.shorter('a b c d e', {relaxes: 3}), null);            // the limit
});

test('a search with no rows goes to fewer words or the next query, and the shell hears after each category', () => {
  const search = slice('async function search(', 'async function nextQuery(');
  assert.match(search, /if \(state !== 'rows'\) \{[\s\S]*shorter\(query, cursor\)[\s\S]*return nextQuery\(/);
  assert.match(search, /const query = cursor\.relaxed \|\| job\.queries\[cursor\.q\]/);
  assert.match(search, /message: `\$\{category\} read`/);
  assert.match(slice('async function nextQuery(', 'async function run('), /relaxed: null, relaxes: 0/);
});

test('an empty result is also read from the result count', () => {
  assert.match(driver, /pagerTitleCell em/);
  assert.match(driver, /=== '0'/);
});
