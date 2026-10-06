"""Explicit metadata preconditions for legacy tests of ranking/feedback/Route.

These synthetic fixtures report English, independently of UI language or title.
Eligibility tests must supply their own reports and never call this helper.
No production default or eligibility rule is patched.
"""
def english_papers(app, project_id=None):
    project_id = project_id or app.get_default_project_id()
    app.set_project_language(project_id, 'stem', ['en'])
    app.store.conn.execute('''UPDATE papers SET metadata_language='en',
        metadata_language_source='synthetic test fixture' WHERE metadata_language IS NULL
        AND key IN (SELECT paper_key FROM project_papers WHERE project_id=?)''', (project_id,))
    app.store.conn.commit()
