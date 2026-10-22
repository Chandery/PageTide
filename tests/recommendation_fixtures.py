"""Explicit metadata preconditions for legacy tests of ranking/feedback/Route.

These synthetic fixtures report English, independently of UI language or title.
Eligibility tests must supply their own reports and never call this helper.
No production default or eligibility rule is patched.

A paper with no PDF source is never recommended, so by default this helper also gives each synthetic paper that has no
source information at all (no arXiv id, no open-access report) a direct PDF link. A paper that already carries an open-access
report, even one with nothing to open, is left as it is. Tests of the no-PDF-source rule pass pdf_source=False.
"""
import json

SYNTHETIC_OA = {'pdf_urls': ['https://example.org/synthetic.pdf'], 'landing_page': None}   # for papers a test builds itself
SYNTHETIC_PDF = json.dumps(SYNTHETIC_OA)


def english_papers(app, project_id=None, pdf_source=True):
    project_id = project_id or app.get_default_project_id()
    app.set_project_language(project_id, 'stem', ['en'])
    app.store.conn.execute('''UPDATE papers SET metadata_language='en',
        metadata_language_source='synthetic test fixture' WHERE metadata_language IS NULL
        AND key IN (SELECT paper_key FROM project_papers WHERE project_id=?)''', (project_id,))
    if pdf_source:
        app.store.conn.execute('''UPDATE papers SET oa_json=? WHERE oa_json IS NULL AND arxiv_id IS NULL
            AND key IN (SELECT paper_key FROM project_papers WHERE project_id=?)''', (SYNTHETIC_PDF, project_id))
    app.store.conn.commit()


def set_user_settings(app, **values):
    """Merge owner preferences into the app's settings.json, as the Settings page would write them."""
    import json
    from pathlib import Path
    path = Path(app.data) / 'settings.json'
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        current = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        current = {}
    path.write_text(json.dumps({**current, **values}), encoding='utf-8')


def legacy_recommendation_settings(app, route_beta=False):
    """Fixtures dated in the past predate the hotspot default (the last 30 days): here the owner chose 'all time'.
    route_beta=True also switches the beta learning-map mode on."""
    set_user_settings(app, timePreference='all', **({'routeBeta': True} if route_beta else {}))
