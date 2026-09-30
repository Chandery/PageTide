from tests.test_profile_insights import ProfileInsightsTests

class ProfileRedesignTests(ProfileInsightsTests):
    def test_hard_is_not_interest_evidence(self):
        self.app.record_feedback('p2', 'too_hard', project_id=self.project)
        data = self.app.profile_insights(self.project)
        self.assertEqual(data['keyword_distribution'], [])
        self.assertEqual(data['signals']['too_hard'], 1)

    def test_project_pins_and_evidence_isolation(self):
        other = self.app.projects.create_project('Other', keywords=['vision'])
        self.app.pin_terms(['planning'], self.project)
        self.assertEqual(self.app.profile(other)['pinned_terms'], ['vision'])
        self.app.record_feedback('p1', 'useful', project_id=self.project)
        self.assertEqual(self.app.profile_evidence(other, 'saved')['total'], 0)
        with self.assertRaises(ValueError):
            self.app.undo_feedback(1, other)

    def test_undo_refreshes_counts_and_preserves_saved_paper(self):
        event = self.app.record_feedback('p1', 'useful', project_id=self.project)
        self.app.undo_feedback(event['feedback_id'], self.project)
        data = self.app.profile_insights(self.project)
        self.assertEqual(data['signals']['positive'], 0)
        self.assertEqual(data['signals']['saved'], 1)
        self.assertEqual(data['weekly_change']['stats']['positive'], 0)
        self.assertEqual(data['weekly_change']['stats']['saved'], 1)
        self.assertEqual(data['recent_feedback'], [])

    def test_evidence_pagination_and_validation(self):
        self.app.record_feedback('p1', 'useful', project_id=self.project)
        result = self.app.profile_evidence(self.project, 'term', 'planning')
        self.assertEqual(result['total'], 1)
        self.assertEqual(result['items'][0]['key'], 'p1')
        self.assertIn('useful_feedback', result['items'][0]['sources'])
        with self.assertRaises(ValueError):
            self.app.profile_evidence(self.project, 'invalid')
        with self.assertRaises(ValueError):
            self.app.profile_evidence(self.project, 'term', 'planning', start='2026-01-01T00:00:00+00:00')

class ProfileRedesignHTTPTests(ProfileInsightsTests):
    def test_profile_evidence_contract_is_project_scoped(self):
        self.app.record_feedback('p1', 'useful', project_id=self.project)
        body = self.app.profile_evidence(self.project, 'feedback')
        self.assertEqual(body['total'], 1)
        self.assertEqual(body['items'][0]['feedback_id'], 1)
        self.assertEqual(self.app.profile_evidence(self.project, 'saved')['total'], 1)
