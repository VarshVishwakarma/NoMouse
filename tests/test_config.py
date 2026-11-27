import json

from nomouse.config import AppConfig, load_config, sanitize_config, save_config


def test_sanitize_clamps_bad_numeric_settings():
    config = AppConfig(cursor_smoothing=99.0, active_margin=-20.0, scroll_max_speed=-1.0, drag_hold_s=0.0)
    checked = sanitize_config(config)
    assert checked.cursor_smoothing == 1.0
    assert checked.active_margin == 0.0
    assert checked.scroll_max_speed == 1.0
    assert checked.drag_hold_s == 0.25


def test_load_config_ignores_unknown_keys_and_clamps_ranges(tmp_path):
    config_path = tmp_path / 'settings.json'
    config_path.write_text(json.dumps({'cursor_smoothing': -3, 'active_margin': 0.8, 'extra': 'ignored'}))
    config = load_config(config_path)
    assert config.cursor_smoothing == 0.0
    assert config.active_margin == 0.35
    assert not hasattr(config, 'extra')


def test_save_config_writes_validated_settings(tmp_path):
    config_path = tmp_path / 'nested' / 'settings.json'
    save_config(AppConfig(scroll_full_speed_px=-2), config_path)
    assert config_path.exists()
    saved = json.loads(config_path.read_text())
    assert saved['scroll_full_speed_px'] == 40.0


def test_default_config_path_does_not_depend_on_working_directory(tmp_path, monkeypatch):
    from nomouse.config import DEFAULT_CONFIG_PATH

    monkeypatch.chdir(tmp_path)
    assert DEFAULT_CONFIG_PATH.is_absolute()
    assert DEFAULT_CONFIG_PATH.name == "settings.json"
    config = load_config()  # must find the project's settings, not <cwd>/config/settings.json
    assert config.camera_width == 640


def test_booleans_are_not_accepted_as_integer_settings(tmp_path):
    config_path = tmp_path / "settings.json"
    config_path.write_text(json.dumps({"camera_index": True, "click_confirm_frames": 5}))
    config = load_config(config_path)
    assert config.camera_index == 0          # fell back to the default instead of 1
    assert config.click_confirm_frames == 5


def test_save_is_atomic_and_round_trips(tmp_path):
    config_path = tmp_path / "settings.json"
    original = AppConfig(cursor_smoothing=0.5, show_landmarks=False, screen_edge_inset_px=4)
    save_config(original, config_path)
    assert not list(tmp_path.glob("*.tmp")), "temporary file must not be left behind"
    assert load_config(config_path) == original


def test_malformed_json_falls_back_to_defaults(tmp_path, capsys):
    config_path = tmp_path / "settings.json"
    config_path.write_text("{not json")
    assert load_config(config_path) == AppConfig()
    assert "using defaults" in capsys.readouterr().out


def test_shipped_settings_file_is_valid_and_matches_defaults():
    from nomouse.config import DEFAULT_CONFIG_PATH

    raw = json.loads(DEFAULT_CONFIG_PATH.read_text(encoding="utf-8"))
    from dataclasses import fields

    known = {f.name for f in fields(AppConfig)}
    assert set(raw) <= known, f"unknown keys in config/settings.json: {set(raw) - known}"
    assert load_config(DEFAULT_CONFIG_PATH) == AppConfig()


def test_installed_copy_uses_per_user_settings_not_site_packages(tmp_path, monkeypatch):
    from nomouse import config as config_module

    fake_site_packages = tmp_path / "site-packages"
    fake_site_packages.mkdir()
    monkeypatch.setattr(config_module, "PROJECT_ROOT", fake_site_packages)  # no main.py next to it
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    path = config_module.default_config_path()
    assert path == tmp_path / "appdata" / "NoMouse" / "settings.json"
    save_config(AppConfig(cursor_smoothing=0.6))  # default location, must not touch site-packages
    assert load_config().cursor_smoothing == 0.6
    assert not list(fake_site_packages.iterdir())


def test_settings_files_from_before_rate_scrolling_still_load(tmp_path):
    # 2.5.0 and earlier shipped these stroke-scroll keys; they are now ignored, not errors.
    config_path = tmp_path / "settings.json"
    config_path.write_text(json.dumps({
        "scroll_trigger_px": 48.0, "scroll_rearm_radius_px": 24.0, "scroll_rearm_stable_frames": 3,
        "scroll_gain": 0.06, "scroll_reversal_delay_s": 0.45, "two_finger_hold_for_scroll_s": 0.65,
        "cursor_smoothing": 0.5,
    }))
    config = load_config(config_path)
    assert config.cursor_smoothing == 0.5
    assert config.scroll_max_speed == AppConfig().scroll_max_speed


def test_scroll_wheel_step_and_invert_are_validated(tmp_path):
    config_path = tmp_path / "settings.json"
    config_path.write_text(json.dumps({"scroll_wheel_step": 9999, "scroll_invert": "yes"}))
    config = load_config(config_path)
    assert config.scroll_wheel_step == 120
    assert config.scroll_invert is False  # non-bool falls back to the default
