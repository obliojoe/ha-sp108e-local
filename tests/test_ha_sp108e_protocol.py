import importlib.util
import sys
import unittest
from pathlib import Path


def load_protocol_module():
    root = Path(__file__).parents[1]
    path = root / "home-assistant" / "custom_components" / "sp108e_local" / "protocol.py"
    if not path.exists():
        path = root / "custom_components" / "sp108e_local" / "protocol.py"
    spec = importlib.util.spec_from_file_location("ha_sp108e_protocol", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


protocol = load_protocol_module()


def load_color_order_module():
    root = Path(__file__).parents[1]
    base = root / "home-assistant" / "custom_components" / "sp108e_local"
    if not base.exists():
        base = root / "custom_components" / "sp108e_local"
    const_spec = importlib.util.spec_from_file_location("sp108e_local.const", base / "const.py")
    const_module = importlib.util.module_from_spec(const_spec)
    sys.modules[const_spec.name] = const_module
    const_spec.loader.exec_module(const_module)

    spec = importlib.util.spec_from_file_location("sp108e_local.color_order", base / "color_order.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


color_order = load_color_order_module()


class HASP108EProtocolTests(unittest.TestCase):
    def test_read_frames(self):
        self.assertEqual(protocol.get_name_frame(), bytes.fromhex("38 00 00 00 77 83"))
        self.assertEqual(protocol.get_settings_frame(), bytes.fromhex("38 00 00 00 10 83"))

    def test_write_frames(self):
        self.assertEqual(protocol.toggle_power_frame(), bytes.fromhex("38 00 00 00 aa 83"))
        self.assertEqual(protocol.brightness_frame(255), bytes.fromhex("38 ff 00 00 2a 83"))
        self.assertEqual(protocol.speed_frame(184), bytes.fromhex("38 b8 00 00 03 83"))
        self.assertEqual(protocol.color_frame(255, 15, 67), bytes.fromhex("38 ff 0f 43 22 83"))
        self.assertEqual(protocol.mode_frame(211), bytes.fromhex("38 d3 00 00 2c 83"))

    def test_parse_name_response(self):
        self.assertEqual(
            protocol.parse_name_response(bytes.fromhex("00 53 50 31 30 38 45 5f 46 41 43 42 38 38")),
            "SP108E_FACB88",
        )

    def test_parse_settings_response(self):
        settings = protocol.parse_settings_response(bytes.fromhex("38 01 d3 b8 ff 00 00 4f 00 01 ff 0f 43 03 00 00 83"))
        self.assertTrue(settings.is_on)
        self.assertEqual(settings.brightness_raw, 255)
        self.assertEqual(settings.color_rgb, (255, 15, 67))
        self.assertEqual(settings.color_hex, "ff0f43")
        self.assertEqual(settings.led_count, 79)
        self.assertEqual(settings.segment_count, 1)

    def test_invalid_settings_response(self):
        with self.assertRaises(protocol.Sp108eProtocolError):
            protocol.parse_settings_response(bytes.fromhex("38 00 83"))

    def test_color_order_mapping(self):
        self.assertEqual(color_order.map_rgb_to_device((1, 2, 3), "RGB"), (1, 2, 3))
        self.assertEqual(color_order.map_rgb_to_device((1, 2, 3), "GRB"), (2, 1, 3))
        self.assertEqual(color_order.map_rgb_from_device((2, 1, 3), "GRB"), (1, 2, 3))


if __name__ == "__main__":
    unittest.main()
