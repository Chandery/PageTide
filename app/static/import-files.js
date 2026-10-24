/* What the import page does with the files a person picked or dropped.
   Pure functions, no DOM and no network, so they are tested from Node: which files are PDFs, which are
   export files of a reference manager, what is already in the batch, and how a dropped folder is walked.
   The folder structure is never interpreted here: the server turns relative paths into categories, so the
   preview a person sees is the one that will be applied. */
(function (root, factory) {
  const api = factory();
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else root.PTImportFiles = api;
})(this, function () {
  'use strict';

  const MB = 1024 * 1024;
  const MAX_BYTES = 60 * MB;     // the server's per-file limit
  const MAX_FILES = 2000;        // the server's per-batch limit
  const CONCURRENCY = 2;         // PDFs read and uploaded at once: pdf.js is memory hungry on a small machine
  const HEADER_LIMIT = 4096;
  const WALK_LIMIT = 20000;      // entries read from one drop before giving up
  const SIDECAR = { bib: 'bibtex', bibtex: 'bibtex', ris: 'ris', json: 'csljson', csljson: 'csljson' };

  const pathOf = (file) => file.webkitRelativePath || file._path || file.name;
  const extension = (name) => { const dot = String(name).lastIndexOf('.'); return dot < 0 ? '' : name.slice(dot + 1).toLowerCase(); };
  const isHidden = (segments) => segments.some((s) => s.startsWith('.') || s === '__MACOSX');

  // The same shape the server stores (NFC, whitespace collapsed), so a file is recognised as already uploaded.
  function canonical(path) {
    return String(path || '').normalize('NFC').replace(/\\/g, '/').split('/')
      .map((s) => s.replace(/[\x00-\x1f\x7f\s]+/g, ' ').trim()).filter((s) => s && s !== '.').join('/');
  }

  function classify(files) {
    const out = { pdfs: [], sidecars: [], skipped: [], ignored: 0 };
    for (const file of files) {
      const path = pathOf(file);
      const segments = path.split('/');
      if (isHidden(segments)) { out.ignored += 1; continue; }
      const ext = extension(file.name);
      if (ext === 'pdf' || file.type === 'application/pdf') {
        if (!file.size) out.skipped.push({ path, reason: 'empty' });
        else if (file.size > MAX_BYTES) out.skipped.push({ path, reason: 'too_large' });
        else out.pdfs.push({ file, path });
      } else if (SIDECAR[ext] && segments.length <= 2) {   // beside the PDFs, not inside some attachment folder
        out.sidecars.push({ file, path, format: SIDECAR[ext] });
      } else out.ignored += 1;
    }
    return out;
  }

  // The first folder all the files share ('' when they were picked one by one or come from several folders).
  function rootOf(paths) {
    if (!paths.length) return '';
    const heads = new Set();
    for (const path of paths) {
      const parts = path.split('/');
      if (parts.length < 2) return '';
      heads.add(parts[0]);
    }
    return heads.size === 1 ? [...heads][0] : '';
  }

  const rowKey = (path, size, modified) => `${canonical(path)}\u0000${size}\u0000${modified}`;
  const resumeSet = (rows) => new Set((rows || []).map(([path, size, modified]) => rowKey(path, size, modified)));
  const alreadyUploaded = (held, item) => held.has(rowKey(item.path, item.file.size, item.file.lastModified));

  // Percent-encoded JSON for a request header: short, typed, and always under the limit.
  function encodeHints(hints) {
    if (!hints || typeof hints !== 'object') return '';
    const clean = {};
    if (hints.doi) clean.doi = String(hints.doi).slice(0, 300);
    if (hints.arxiv) clean.arxiv = String(hints.arxiv).slice(0, 300);
    const titles = (hints.titles || []).filter(Boolean).slice(0, 3).map((t) => String(t).slice(0, 300));
    if (titles.length) clean.titles = titles;
    if (!Object.keys(clean).length) return '';
    let encoded = encodeURIComponent(JSON.stringify(clean));
    while (encoded.length > HEADER_LIMIT && clean.titles && clean.titles.length) {
      clean.titles.pop();
      if (!clean.titles.length) delete clean.titles;
      encoded = encodeURIComponent(JSON.stringify(clean));
    }
    return encoded.length > HEADER_LIMIT ? '' : encoded;
  }

  // ~/Zotero/storage holds one 8-character folder per item, not a collection: its folder names are not categories.
  function looksLikeZoteroStorage(paths) {
    const keys = paths.map((p) => p.split('/')).filter((parts) => parts.length >= 3).map((parts) => parts[1]);
    const matching = keys.filter((key) => /^[A-Z0-9]{8}$/.test(key)).length;
    return matching >= 3 && matching / keys.length >= 0.8;
  }

  // A dropped folder arrives as FileSystemEntry objects; readEntries returns a page at a time until it returns [].
  async function walkEntries(entries, options = {}) {
    const limit = options.limit || WALK_LIMIT;
    const found = [];
    const readAll = (reader) => new Promise((resolve) => {
      const all = [];
      const next = () => reader.readEntries((batch) => {
        if (!batch.length) return resolve(all);
        all.push(...batch);
        next();
      }, () => resolve(all));   // a folder that cannot be read is skipped, not fatal
      next();
    });
    async function visit(entry, prefix) {
      if (found.length >= limit) return;
      const path = prefix ? `${prefix}/${entry.name}` : entry.name;
      if (entry.isFile) {
        const file = await new Promise((resolve) => entry.file(resolve, () => resolve(null)));
        if (file) { file._path = path; found.push(file); }
      } else if (entry.isDirectory) {
        for (const child of await readAll(entry.createReader())) {
          if (found.length >= limit) break;
          await visit(child, path);
        }
      }
    }
    for (const entry of entries) await visit(entry, '');
    return found;
  }

  return { classify, rootOf, resumeSet, alreadyUploaded, encodeHints, looksLikeZoteroStorage, walkEntries,
    pathOf, canonical, CONCURRENCY, MAX_FILES, MAX_BYTES };
});
