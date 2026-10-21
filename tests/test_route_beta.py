"""Learning-map mode is a beta feature behind one setting (routeBeta, default off).

Rules under test: with the setting off every recommendation path is hotspot mode (profile + sparse ranking over
recent papers, zero model tokens), the stored map and its progress are kept untouched, and the learning-map parts of
the profile report disappear. Turning the setting on restores the project's own mode. Hotspot defaults (30 days,
new-paper boost 0.5) apply only when the owner has not chosen a value.
"""
import datetime
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_route_runtime import Fixture
from recommendation_fixtures import english_papers
from app import profile_insights, server, user_settings


def write_settings(app, **values):
    path = Path(app.data) / "settings.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(values))


def day(offset):
    return (datetime.date.today() - datetime.timedelta(days=offset)).isoformat()


class SettingTests(unittest.TestCase):
    def test_route_beta_is_off_unless_explicitly_true(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            self.assertFalse(user_settings.route_beta(tmp))
            Path(tmp, "settings.json").write_text(json.dumps({"routeBeta": "yes"}))
            self.assertFalse(user_settings.route_beta(tmp))
            Path(tmp, "settings.json").write_text(json.dumps({"routeBeta": True}))
            self.assertTrue(user_settings.route_beta(tmp))

    def test_validate_accepts_only_a_boolean(self):
        self.assertEqual(user_settings.validate({"routeBeta": True}), {"routeBeta": True})
        for bad in ("true", 1, None):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    user_settings.validate({"routeBeta": bad})


class GateTests(Fixture):
    owner_settings = False

    def test_off_by_default_hides_the_map_from_every_recommendation_path(self):
        self.enable()
        self.assertIsNone(self.app._route_state(self.pid))
        self.assertIsNone(self.app.home_route(self.pid))

    def test_on_restores_the_project_mode(self):
        self.enable()
        write_settings(self.app, routeBeta=True)
        self.assertIsNotNone(self.app._route_state(self.pid))
        self.assertTrue(self.app.home_route(self.pid)["enabled"])

    def test_turning_it_off_keeps_the_stored_map_and_progress(self):
        self.enable(mastered=["Crystal basics"])
        write_settings(self.app, routeBeta=True)
        before = self.app.route_get(self.pid)
        write_settings(self.app, routeBeta=False)
        after = self.app.route_get(self.pid)
        self.assertEqual(before["graph"], after["graph"])
        self.assertEqual(before["manual"], after["manual"])
        self.assertEqual(before["progress"], after["progress"])

    def test_off_batch_has_no_learning_map_cards(self):
        self.enable(mastered=["Crystal basics"])
        for i in range(6):
            self.paper(f"e{i}", f"Epitaxial growth {i}", "epitaxy epitaxial growth", published=day(i + 1))
        english_papers(self.app, self.pid)
        result = self.app.build_batch(project_id=self.pid)
        self.assertTrue(result["cards"])
        self.assertTrue(all(c["mode"] == "sparse" and not c["route"] for c in result["cards"]))

    def test_profile_report_has_no_learning_map_section_when_off(self):
        self.enable()
        papers = {p["key"]: dict(p) for p in self.app.store.papers()}
        self.assertIsNone(profile_insights.learning_map(self.app, self.pid, papers, []))
        write_settings(self.app, routeBeta=True)
        self.assertIsNotNone(profile_insights.learning_map(self.app, self.pid, papers, []))


class HotspotTests(Fixture):
    owner_settings = False

    def keys(self, **settings):
        write_settings(self.app, **settings)
        english_papers(self.app, self.pid)
        return [c["key"] for c in self.app.build_batch(project_id=self.pid, limit=5)["cards"]]

    def seed(self):
        for i in range(3):
            self.paper(f"new{i}", f"Crystal lattice growth {i}", "crystal lattice growth", published=day(2 + i))
        self.paper("old", "Crystal lattice growth classic", "crystal lattice growth", published=day(200))

    def test_default_window_is_thirty_days(self):
        self.seed()
        keys = self.keys()
        self.assertEqual(sorted(keys), ["new0", "new1", "new2"])

    def test_the_owner_time_preference_wins(self):
        self.seed()
        self.assertIn("old", self.keys(timePreference="all"))

    def test_default_boost_puts_the_newest_first(self):
        self.seed()
        self.assertEqual(self.keys()[0], "new0")

    def test_the_owner_boost_wins(self):
        self.assertEqual(user_settings.boost("/nonexistent", 0.5), 0.5)
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "settings.json").write_text(json.dumps({"newPaperBoost": 0.1}))
            self.assertEqual(user_settings.boost(tmp, 0.5), 0.1)


class ServedPageTests(unittest.TestCase):
    """Every HTML page is told, before it renders, whether the beta is on: that is what hides the map entry points."""
    def setUp(self):
        import tempfile, threading, urllib.request
        from app import server
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        (root / "harness").mkdir()
        (root / "harness" / "seeds.json").write_text(json.dumps({"seeds": []}))
        (root / "harness" / "budget.json").write_text(
            (Path(__file__).resolve().parents[1] / "harness" / "budget.json").read_text())
        self.root = root
        self.httpd = server.build_server(port=0, root=str(root))
        self.port = self.httpd.server_address[1]
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        self.addCleanup(self.httpd.server_close)
        self.addCleanup(self.httpd.shutdown)
        self.urlopen = urllib.request.urlopen

    def page(self, name):
        with self.urlopen(f"http://127.0.0.1:{self.port}/{name}", timeout=5) as response:
            return response.read().decode()

    def test_pages_say_the_beta_is_off_by_default_and_hide_marked_elements(self):
        for name in ("index.html", "project_creation.html", "project.html", "route.html", "settings.html"):
            with self.subTest(page=name):
                html = self.page(name)
                self.assertIn("window.PDH_ROUTE_BETA=false", html)
                self.assertNotIn("classList.add('route-beta')", html)
                self.assertIn("html:not(.route-beta) [data-route-beta]", html)

    def test_pages_say_the_beta_is_on_after_the_owner_turns_it_on(self):
        data = Path(server.data_dir(str(self.root)))
        data.mkdir(parents=True, exist_ok=True)
        (data / "settings.json").write_text(json.dumps({"routeBeta": True}))
        html = self.page("index.html")
        self.assertIn("window.PDH_ROUTE_BETA=true", html)
        self.assertIn("classList.add('route-beta')", html)

    def test_the_setting_is_saved_and_read_back_through_the_settings_api(self):
        import urllib.request
        request = urllib.request.Request(
            f"http://127.0.0.1:{self.port}/api/user_settings", data=json.dumps({"settings": {"routeBeta": True}}).encode(),
            headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(request, timeout=5) as response:
            self.assertEqual(json.loads(response.read())["status"], "saved")
        with urllib.request.urlopen(f"http://127.0.0.1:{self.port}/api/user_settings", timeout=5) as response:
            self.assertIs(json.loads(response.read())["settings"]["routeBeta"], True)
        self.assertIn("window.PDH_ROUTE_BETA=true", self.page("index.html"))


if __name__ == "__main__":
    unittest.main()
