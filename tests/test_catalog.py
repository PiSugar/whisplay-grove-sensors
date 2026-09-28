from whisplay_grove.catalog import PERIPHERALS, find_conflicts, get_peripheral
from whisplay_grove.dashboard import catalog_candidates, format_value


def test_catalog_slugs_are_unique():
    slugs = [item.slug for item in PERIPHERALS]
    assert len(slugs) == len(set(slugs))


def test_catalog_covers_both_port_x_transports():
    assert {item.transport for item in PERIPHERALS} == {"i2c", "uart"}
    assert len(PERIPHERALS) >= 80


def test_known_units_and_pisugar_conflict():
    assert get_peripheral("ultrasonic-i2c").addresses == (0x57,)
    assert get_peripheral("nfc").addresses == (0x50,)
    assert get_peripheral("joystick2").support == "decoded"
    assert get_peripheral("scroll").addresses == (0x40,)
    assert get_peripheral("gps-v11").baudrate == 115200
    assert "TVOC" in {item.name.split("/")[0] for item in find_conflicts(0x58)}


def test_dashboard_covers_catalog_and_formats_values():
    assert len(PERIPHERALS) >= 80
    assert {item.slug for item in catalog_candidates(0x40)} >= {"scroll", "ina226"}
    assert format_value(True) == "YES"
    assert format_value(12.340) == "12.34"
