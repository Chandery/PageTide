"""Shared fakes for the library-import tests: staged PDF bytes, OpenAlex works, and a client that never touches the network."""
from app.sources import SourceError


def pdf(n):
    return b"%PDF-1.7\n" + f"paper {n}".encode() * 40


def work(n, title=None, doi=None, date="2020-05-01"):
    return {"id": f"https://openalex.org/W{n}", "doi": doi or f"https://doi.org/10.1000/p{n}",
            "title": title or f"Paper number {n} about learning", "ids": {}, "publication_date": date}


class FakeClient:
    def __init__(self):
        self.calls = []
        self.dois, self.titles, self.arxiv = {}, {}, {}
        self.works = self.arxiv   # work(identifier) answers from this map: arXiv DOIs and plain DOIs alike
        self.work_errors = {}     # identifier -> the SourceError work() raises for it
        self.limit = None
        self.fail = None          # (call name, SourceError) raised once when that call is made
        self.fail_after = 0

    def _maybe_fail(self, name):
        if self.fail and self.fail[0] == name:
            if self.fail_after <= 0:
                raise self.fail[1]
            self.fail_after -= 1

    def works_by_dois(self, dois):
        self.calls.append(("dois", list(dois)))
        self._maybe_fail("dois")
        return [self.dois[d] for d in dois if d in self.dois]

    def work(self, identifier):
        self.calls.append(("work", identifier))
        self._maybe_fail("work")
        if identifier in self.work_errors:
            raise self.work_errors[identifier]
        if identifier in self.arxiv:
            return self.arxiv[identifier]
        raise SourceError("missing", "not_found")

    def find_arxiv(self, arxiv_id):
        self.calls.append(("find_arxiv", arxiv_id))
        raise SourceError("missing", "not_found")

    def title_lookup(self, title):
        self.calls.append(("title", title))
        self._maybe_fail("title")
        return list(self.titles.get(title, []))

    def rate_limit(self):
        return self.limit

    def names(self):
        return [c[0] for c in self.calls]
