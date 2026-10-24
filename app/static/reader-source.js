(function(root) {
  'use strict';
  async function hash(doc, cryptoApi=root.crypto) {
    const bytes=await doc.getData();
    if (!bytes || bytes.byteLength>128*1024*1024) throw new Error('PDF 太大，无法读取正文');
    if (!cryptoApi?.subtle) throw new Error('无法确认正文来自哪个 PDF 版本');
    const digest=await cryptoApi.subtle.digest('SHA-256',bytes);
    return [...new Uint8Array(digest)].map(x=>x.toString(16).padStart(2,'0')).join('');
  }
  const api={hash};
  if (typeof module==='object' && module.exports) module.exports=api;
  root.PTReaderSource=api;
})(typeof window==='object'?window:globalThis);
