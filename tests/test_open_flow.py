import unittest

from rips_ai.android_state import (
    activity_package,
    return_to_package_commands,
    start_activity_commands,
    window_focus_probe_command,
)
from rips_ai.open_flow import (
    gallery_shell_plan_lines,
    gallery_plan_parameters,
    open_pack_dry_run_lines,
    open_pack_sequence,
    parse_point_override,
)


def sample_flow() -> dict[str, object]:
    return {
        "vault_gallery": {
            "columns": 2,
            "rows": 2,
            "pages": 1,
            "first_card_center": [100, 200],
            "x_step": 50,
            "y_step": 60,
            "long_press_ms": 900,
            "between_cards_ms": 500,
        },
        "gestures": {
            "tap_buy": {"at": [540, 1950]},
            "spin_picker_left": {
                "from": [820, 1220],
                "to": [260, 1220],
                "duration_ms": 600,
                "repeat_count": 2,
                "repeat_delay_ms": 180,
                "settle_ms": 1200,
            },
            "spin_picker_right": {
                "from": [260, 1220],
                "to": [820, 1220],
                "duration_ms": 600,
            },
            "tap_center_pack": {"at": [540, 1220]},
            "slice_left_to_right": {
                "from": [60, 1240],
                "to": [1020, 1240],
                "duration_ms": 700,
            },
            "speed_up_reveal_swipe": {
                "from": [60, 1320],
                "to": [1020, 1320],
                "duration_ms": 250,
                "delay_ms": 350,
            },
            "vault_gallery_scroll_next": {
                "from": [540, 1850],
                "to": [540, 640],
                "duration_ms": 800,
            },
        },
    }


class AndroidStateTests(unittest.TestCase):
    def test_android_shell_helpers_quote_targets(self):
        self.assertEqual(activity_package("com.example.app/.Main"), "com.example.app")
        self.assertEqual(
            start_activity_commands("com.example.app/.Main"),
            ["am start -n com.example.app/.Main >/dev/null", "sleep 1"],
        )
        self.assertEqual(
            return_to_package_commands("codex.app"),
            ["monkey -p codex.app 1 >/dev/null", "sleep 1"],
        )
        self.assertEqual(
            window_focus_probe_command(),
            'dumpsys window | grep -E "mCurrentFocus|mFocusedApp" | head -n 5',
        )


class OpenFlowTests(unittest.TestCase):
    def test_parse_point_override_accepts_xy(self):
        self.assertEqual(parse_point_override("540,1990", "--buy-tap"), (540, 1990))

    def test_parse_point_override_rejects_bad_values(self):
        with self.assertRaisesRegex(ValueError, "X,Y format"):
            parse_point_override("540", "--buy-tap")
        with self.assertRaisesRegex(ValueError, "integer"):
            parse_point_override("x,y", "--buy-tap")

    def test_open_pack_sequence_matches_legacy_full_flow(self):
        command = open_pack_sequence(
            flow=sample_flow(),
            activity="com.triumpharcade.tcg/.MainActivity",
            return_package="codex.app",
            stay_in_rips=False,
            picker_spin="left",
            stage="full",
        )

        self.assertIn("am start -n com.triumpharcade.tcg/.MainActivity >/dev/null", command)
        self.assertIn("input tap 540 1950", command)
        self.assertEqual(command.count("input swipe 820 1220 260 1220 600"), 2)
        self.assertIn("sleep 0.18", command)
        self.assertIn("sleep 1.20", command)
        self.assertIn("input tap 540 1220", command)
        self.assertIn("input swipe 60 1240 1020 1240 700", command)
        self.assertIn("monkey -p codex.app 1 >/dev/null", command)
        self.assertTrue(command.endswith(window_focus_probe_command()))

    def test_open_pack_sequence_supports_buy_tap_override(self):
        command = open_pack_sequence(
            flow=sample_flow(),
            activity="com.triumpharcade.tcg/.MainActivity",
            return_package="codex.app",
            stay_in_rips=True,
            picker_spin="left",
            stage="tap-buy",
            buy_tap=(540, 1990),
        )

        self.assertIn("input tap 540 1990", command)
        self.assertNotIn("monkey -p codex.app", command)

    def test_open_pack_dry_run_lines_format_command_steps(self):
        lines = open_pack_dry_run_lines(
            stage="full",
            pack_name="$1 pack",
            pack_id="one_dollar",
            price="$1.00",
            tracked_bank_before="$14.00",
            planned_bank_after_buy="$13.00",
            planned_pending="one_dollar at $1.00",
            command=(
                "am start -n com.triumpharcade.tcg/.MainActivity >/dev/null; "
                "input tap 540 1950"
            ),
            confirmed_buy_screen=False,
            purchase_observed=False,
        )

        self.assertEqual(lines[0], "dry-run: device-open-pack")
        self.assertIn(
            "screen confirmation: execution still requires --confirmed-buy-screen",
            lines,
        )
        self.assertIn("  input tap 540 1950", lines)

    def test_gallery_plan_parameters_uses_flow_defaults(self):
        parameters, points, scroll_command = gallery_plan_parameters(sample_flow())

        self.assertEqual(parameters["columns"], 2)
        self.assertEqual(parameters["first_x"], 100)
        self.assertEqual(len(points), 4)
        self.assertEqual(scroll_command, "input swipe 540 1850 540 640 800")

    def test_gallery_shell_plan_lines_formats_long_press_actions(self):
        parameters, points, scroll_command = gallery_plan_parameters(sample_flow())

        lines = gallery_shell_plan_lines(parameters, points, scroll_command)

        self.assertIn("# Card 1: page 1, row 1, column 1", lines)
        self.assertIn("input swipe 100 200 100 200 900", lines)
        self.assertIn("input keyevent BACK", lines)

    def test_gallery_plan_parameters_requires_first_point_pair(self):
        with self.assertRaisesRegex(ValueError, "both --first-x and --first-y"):
            gallery_plan_parameters(sample_flow(), first_x=123)


if __name__ == "__main__":
    unittest.main()
