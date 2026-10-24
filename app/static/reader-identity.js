(function(root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.PTReaderIdentity = api;
})(typeof window !== 'undefined' ? window : this, function() {
  function matches(a, b) {
    return !!a && !!b && a.key === b.key && a.project_id === b.project_id && a.pdf_sha256 === b.pdf_sha256;
  }
  function popupPosition(rect, size, viewport) {
    const margin = 10, anchor = rect || {left: 40, bottom: 100};
    return {left: Math.min(Math.max(margin, anchor.left), Math.max(margin, viewport.width - size.width - margin)),
      top: Math.min(Math.max(margin, anchor.bottom + margin), Math.max(margin, viewport.height - size.height - margin))};
  }
  function readingProject(owners, scope, current) {
    if (scope && scope !== 'all' && owners.includes(scope)) return scope;
    if (owners.includes(current)) return current;
    return owners.length === 1 ? owners[0] : null;
  }
  return {matches, popupPosition, readingProject};
});
