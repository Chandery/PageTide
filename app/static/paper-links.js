/* Links to outside tools for one paper. Pure string building: nothing is requested from here. A link only
   opens (in a new tab) when the person clicks it, so no paper title or id leaves the app until then. */
(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.PDHLinks = api;
})(typeof window !== 'undefined' ? window : this, function () {
  const ARXIV = /^(?:\d{4}\.\d{4,5}|[a-z-]+(?:\.[A-Za-z]{2})?\/\d{7})(?:v\d+)?$/;
  const DOI = /^10\.\d{4,9}\/\S+$/;

  /* Connected Papers has no public API and no stable address for a paper, so the link is its search page filled in
     with the most reliable thing we know about the paper: the arXiv address, else the DOI, else the title. The
     site decides whether it finds the paper; this app cannot know, and does not claim that it does. */
  function connectedPapersURL(paper) {
    if (!paper) return null;
    const arxiv = String(paper.arxiv_id || '').trim().replace(/^arxiv:/i, '');
    const doi = String(paper.doi || '').trim().replace(/^https?:\/\/(?:dx\.)?doi\.org\//i, '').replace(/^doi:/i, '');
    const title = String(paper.title || '').replace(/\s+/g, ' ').trim();
    let query = null;
    if (ARXIV.test(arxiv)) query = `https://arxiv.org/abs/${arxiv}`;
    else if (DOI.test(doi)) query = doi;
    else if (title.length >= 12) query = title.slice(0, 200);
    return query ? `https://www.connectedpapers.com/search?q=${encodeURIComponent(query)}` : null;
  }

  return { connectedPapersURL };
});
