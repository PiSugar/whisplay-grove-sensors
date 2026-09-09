from whisplay_grove.catalog import PERIPHERALS, find_conflicts, get_peripheral


def test_catalog_slugs_are_unique():
    slugs = [item.slug for item in PERIPHERALS]
    assert len(slugs) == len(set(slugs))


def test_catalog_covers_both_port_x_transports():
    assert {item.transport for item in PERIPHERALS} == {"i2c", "uart"}
    assert len(PERIPHERALS) >= 80


def test_known_units_and_pisugar_conflict():
    assert get_peripheral("ultrasonic-i2c").addresses == (0x57,)
    assert get_peripheral("gps-v11").baudrate == 115200
    assert "TVOC" in {item.name.split("/")[0] for item in find_conflicts(0x58)}

