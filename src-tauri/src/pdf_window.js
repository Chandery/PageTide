// Runs in the "download in the app" window (pdf_window.rs, ADR 0047) on every page. It hands the paper's PDF to the app,
// read with the window's own session (the same request the person's browser makes), in 1 MB chunks:
// - on an article page that names its PDF the way publishers do for Google Scholar (<meta name="citation_pdf_url">), that
//   PDF; if the browser will not let the page read it (another site), the window goes to it once instead;
// - when the person clicks a link that looks like a PDF, that link, read from the page while the click goes on;
// - when the window shows a PDF, that PDF. WebKit runs no script in some PDF documents (one sent as an attachment,
//   cyberleninka.ru, 2026-10-26), so the two cases above, which work from the web page, come first.
(() => {
  if (window.top !== window || window.__pageTidePdfWindow) return;
  window.__pageTidePdfWindow = true;
  const CHUNK = 1024 * 1024;
  const invoke = (cmd, args) => window.__TAURI_INTERNALS__.invoke(cmd, args);
  // Dev builds only (the shell sets __pageTideDebug and logs title changes): say what happened.
  const debug = (message) => { if (window.__pageTideDebug) document.title = 'pagetide-debug: ' + message; };

  const base64 = (bytes) => {
    let text = '';
    for (let i = 0; i < bytes.length; i += 0x8000) text += String.fromCharCode.apply(null, bytes.subarray(i, i + 0x8000));
    return btoa(text);
  };

  // true when a PDF was read and handed over.
  async function handOver(url) {
    const response = await fetch(url, { credentials: 'include' });
    if (!response.ok) { debug('fetch ' + response.status); return false; }
    const bytes = new Uint8Array(await response.arrayBuffer());
    if (bytes.length < 5 || String.fromCharCode(...bytes.subarray(0, 5)) !== '%PDF-') { debug('not a PDF, ' + bytes.length + ' bytes'); return false; }
    for (let index = 0, offset = 0; offset < bytes.length; index += 1, offset += CHUNK) {
      let answer;
      try { answer = await invoke('pdf_window_chunk', { index, total: bytes.length, data: base64(bytes.subarray(offset, offset + CHUNK)) }); }
      catch (e) { debug('invoke failed: ' + e); throw e; }
      if (!answer || answer.accepted === false) { debug('refused ' + JSON.stringify(answer)); return false; }
    }
    debug('handed over ' + bytes.length + ' bytes');
    return true;
  }

  async function fromArticlePage() {
    const named = (document.querySelector('meta[name="citation_pdf_url"]') || {}).content;
    if (!named) return;                                   // nothing named: the person clicks the PDF link
    let target;
    try { target = new URL(named, location.href); } catch (e) { return; }
    if (target.protocol !== 'https:' || target.href === location.href) return;
    let handed = false;
    try { handed = await handOver(target.href); } catch (e) { /* another site's PDF: the page may not read it */ }
    if (handed) return;
    const once = 'pagetide-pdf-visited:' + target.href;
    try {
      if (sessionStorage.getItem(once)) return;
      sessionStorage.setItem(once, '1');
    } catch (e) { return; }
    location.assign(target.href);
  }

  // A click on a link that looks like a PDF: read it from this page (same site only; the click itself goes on).
  const looksLikePdf = (url) => /\.pdf(?:$|[?#])|\/pdf(?:\/|$|[?#])|\/download\/|[?&](?:download|pdf)\b/i.test(url.pathname + url.search);
  let clicked = false;
  document.addEventListener('click', (event) => {
    const link = event.target && event.target.closest ? event.target.closest('a[href]') : null;
    if (!link || clicked || !window.__TAURI_INTERNALS__) return;
    let url;
    try { url = new URL(link.href, location.href); } catch (e) { return; }
    if (url.protocol !== 'https:' || url.origin !== location.origin || !looksLikePdf(url)) return;
    clicked = true;
    handOver(url.href).then((ok) => { clicked = ok; }, () => { clicked = false; });
  }, true);

  async function start() {
    if (!window.__TAURI_INTERNALS__) { debug('no IPC in this page'); return; }
    debug('start ' + document.contentType);
    if (document.contentType === 'application/pdf') await handOver(location.href);
    else await fromArticlePage();
  }

  const run = () => start().catch((e) => debug('error: ' + e));   // the person can still save the PDF from the viewer
  if (document.readyState === 'complete') run();
  else window.addEventListener('load', run, { once: true });
})();
