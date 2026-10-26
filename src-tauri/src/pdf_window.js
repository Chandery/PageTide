// Runs in the "download in the app" window (pdf_window.rs, ADR 0047) on every page. On an ordinary page it does nothing:
// the person reads the page and clicks the PDF link. When the window shows a PDF, it reads that PDF once with the
// window's own session (the same request the person's browser makes) and hands it to the app in 1 MB chunks.
(() => {
  if (window.top !== window || window.__pageTidePdfWindow) return;
  window.__pageTidePdfWindow = true;
  const CHUNK = 1024 * 1024;
  const invoke = (cmd, args) => window.__TAURI_INTERNALS__.invoke(cmd, args);

  const base64 = (bytes) => {
    let text = '';
    for (let i = 0; i < bytes.length; i += 0x8000) text += String.fromCharCode.apply(null, bytes.subarray(i, i + 0x8000));
    return btoa(text);
  };

  async function handOver() {
    if (document.contentType !== 'application/pdf' || !window.__TAURI_INTERNALS__) return;
    const response = await fetch(location.href, { credentials: 'include' });
    if (!response.ok) return;
    const bytes = new Uint8Array(await response.arrayBuffer());
    if (bytes.length < 5 || String.fromCharCode(...bytes.subarray(0, 5)) !== '%PDF-') return;
    for (let index = 0, offset = 0; offset < bytes.length; index += 1, offset += CHUNK) {
      const answer = await invoke('pdf_window_chunk', { index, total: bytes.length, data: base64(bytes.subarray(offset, offset + CHUNK)) });
      if (!answer || answer.accepted === false) return;
    }
  }

  const start = () => handOver().catch(() => { /* the person can still save the PDF from the viewer */ });
  if (document.readyState === 'complete') start();
  else window.addEventListener('load', start, { once: true });
})();
