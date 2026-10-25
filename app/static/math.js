/* LaTeX in paper titles and abstracts ($...$, $$...$$, \(...\), \[...\]) drawn with KaTeX (vendor/katex, fetched the
   first time a page shows a formula). Mark an element with data-tex; elements added later are found by an observer.
   Text outside a formula stays text, and a formula KaTeX cannot read stays exactly as written. Titles and abstracts
   are untrusted source text: KaTeX runs with trust off (no \href, \url, \includegraphics) and bounded expansion. */
(function (global) {
'use strict';
// $$..$$ | \[..\] | \(..\) | $..$ — a single-dollar formula may not start or end with a space, so "$5 and $10" stays text.
const MATH = /\$\$([^$]+?)\$\$|\\\[([\s\S]+?)\\\]|\\\(([\s\S]+?)\\\)|\$(?!\s)([^$\n]+?)(?<!\s)\$/g;
const OPTIONS = { throwOnError: true, displayMode: false, trust: false, strict: 'ignore', maxSize: 10, maxExpand: 200 };
let loading = null;

function hasMath(text) { MATH.lastIndex = 0; const found = MATH.test(text || ''); MATH.lastIndex = 0; return found; }

function load() {
  if (global.katex) return Promise.resolve();
  if (!loading) loading = new Promise((resolve, reject) => {
    const css = document.createElement('link');
    css.rel = 'stylesheet'; css.href = '/vendor/katex/katex.min.css';
    const script = document.createElement('script');
    script.src = '/vendor/katex/katex.min.js'; script.onload = resolve; script.onerror = reject;
    document.head.append(css, script);
  });
  return loading;
}

// One text node: each formula KaTeX can draw becomes a .tex span; the rest of the text is kept as text nodes.
function renderText(node) {
  const text = node.nodeValue, parts = [];
  let last = 0, match;
  MATH.lastIndex = 0;
  while ((match = MATH.exec(text))) {
    const tex = match[1] ?? match[2] ?? match[3] ?? match[4];
    const span = document.createElement('span');
    span.className = 'tex';
    try { global.katex.render(tex, span, OPTIONS); } catch { continue; }
    parts.push(text.slice(last, match.index), span);
    last = match.index + match[0].length;
  }
  if (!parts.length) return;
  parts.push(text.slice(last));
  node.replaceWith(...parts.filter((part) => part !== ''));
}

function draw(el) {
  const walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT, {
    acceptNode: (n) => (n.parentElement?.closest('.katex') ? NodeFilter.FILTER_REJECT : NodeFilter.FILTER_ACCEPT) });
  const nodes = [];
  while (walker.nextNode()) if (hasMath(walker.currentNode.nodeValue)) nodes.push(walker.currentNode);
  nodes.forEach(renderText);
}

// Every [data-tex] element in or at `root` that holds a formula; KaTeX is fetched once, on the first one.
function typeset(root) {
  if (!root || root.nodeType !== 1) return;
  const found = [...(root.matches?.('[data-tex]') ? [root] : []), ...root.querySelectorAll('[data-tex]')]
    .filter((el) => !el.dataset.texDone && hasMath(el.textContent));
  if (!found.length) return;
  found.forEach((el) => { el.dataset.texDone = '1'; });
  load().then(() => found.forEach(draw)).catch(() => { /* offline page or missing file: the text stays as written */ });
}

function watch() {
  typeset(document.body);
  new MutationObserver((records) => {
    for (const record of records) {
      record.addedNodes.forEach(typeset);
      const host = record.target.closest?.('[data-tex]');   // new text set on a marked element in place
      if (host && [...record.addedNodes].some((n) => n.nodeType === 3)) { delete host.dataset.texDone; typeset(host); }
    }
  }).observe(document.body, { childList: true, subtree: true });
}
if (typeof document !== 'undefined' && document.addEventListener) {
  if (document.body) watch(); else document.addEventListener('DOMContentLoaded', watch);
}
global.PTMath = { hasMath, typeset, MATH };
})(window);
