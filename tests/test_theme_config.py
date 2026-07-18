"""Tests for theme / display configuration (issue #11)."""
import os
import sys
import unittest


class ThemeConfigTest(unittest.TestCase):
    """Test that theme env vars are respected and presets work."""

    def _import_config(self, env_overrides=None):
        """Fresh import of config with modified environment."""
        if env_overrides is None:
            env_overrides = {}
        # Save original env
        old_env = {k: os.environ.get(k) for k in env_overrides}
        try:
            for k, v in env_overrides.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v
            # Force re-import
            for mod in list(sys.modules.keys()):
                if mod.startswith("statstrip"):
                    sys.modules.pop(mod, None)
            from statstrip import config
            return config
        finally:
            # Restore
            for k, v in old_env.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v

    def test_default_theme_is_cyan(self):
        cfg = self._import_config({})
        self.assertEqual(cfg.BG, "#0a0f1a")
        self.assertEqual(cfg.FG, "#22d3ee")
        self.assertEqual(cfg.FONT_FAMILY, "Consolas")

    def test_theme_preset_mono(self):
        cfg = self._import_config({"STATSTRIP_THEME": "mono"})
        self.assertEqual(cfg.BG, "#1a1a1a")
        self.assertEqual(cfg.FG, "#e0e0e0")
        self.assertEqual(cfg.FONT_FAMILY, "Consolas")

    def test_theme_preset_amber(self):
        cfg = self._import_config({"STATSTRIP_THEME": "amber"})
        self.assertEqual(cfg.BG, "#1a0f00")
        self.assertEqual(cfg.FG, "#ffb800")
        self.assertEqual(cfg.FONT_FAMILY, "Consolas")

    def test_theme_preset_green(self):
        cfg = self._import_config({"STATSTRIP_THEME": "green"})
        self.assertEqual(cfg.BG, "#001a00")
        self.assertEqual(cfg.FG, "#00ff88")
        self.assertEqual(cfg.FONT_FAMILY, "Consolas")

    def test_theme_preset_high_contrast(self):
        cfg = self._import_config({"STATSTRIP_THEME": "high-contrast"})
        self.assertEqual(cfg.BG, "#000000")
        self.assertEqual(cfg.FG, "#ffffff")
        self.assertEqual(cfg.FONT_FAMILY, "Consolas")

    def test_individual_env_vars_override_theme(self):
        # Theme provides a base, individual vars should override
        cfg = self._import_config({
            "STATSTRIP_THEME": "amber",
            "STATSTRIP_FG": "#ff0000",
        })
        self.assertEqual(cfg.FG, "#ff0000")  # override
        self.assertEqual(cfg.BG, "#1a0f00")  # from theme

    def test_individual_env_vars_without_theme(self):
        cfg = self._import_config({
            "STATSTRIP_FG": "#00ff00",
            "STATSTRIP_BG": "#111111",
            "STATSTRIP_FONT": "Monospace",
        })
        self.assertEqual(cfg.FG, "#00ff00")
        self.assertEqual(cfg.BG, "#111111")
        self.assertEqual(cfg.FONT_FAMILY, "Monospace")

    def test_unknown_theme_falls_back_to_default(self):
        cfg = self._import_config({"STATSTRIP_THEME": "does-not-exist"})
        # Should fall back to cyan defaults
        self.assertEqual(cfg.BG, "#0a0f1a")
        self.assertEqual(cfg.FG, "#22d3ee")
        self.assertEqual(cfg.FONT_FAMILY, "Consolas")

    def test_theme_names_constant_exists(self):
        cfg = self._import_config({})
        self.assertIn("cyan", cfg.THEME_NAMES)
        self.assertIn("mono", cfg.THEME_NAMES)
        self.assertIn("amber", cfg.THEME_NAMES)
        self.assertIn("green", cfg.THEME_NAMES)
        self.assertIn("high-contrast", cfg.THEME_NAMES)

    def test_theme_presets_constant_exists(self):
        cfg = self._import_config({})
        self.assertIn("cyan", cfg.THEME_PRESETS)
        self.assertIn("mono", cfg.THEME_PRESETS)
        self.assertEqual(cfg.THEME_PRESETS["cyan"], ("#0a0f1a", "#22d3ee", "Consolas"))


if __name__ == "__main__":
    unittest.main()