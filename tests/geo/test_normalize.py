import pytest

from geo.normalize import name_key, normalize_name, strip_gazetteer_suffix


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Big Cabin", "BIG CABIN"),
        ("  Effingham   ", "EFFINGHAM"),
        ("La Cañada Flintridge", "LA CANADA FLINTRIDGE"),
        ("O'Donnell", "ODONNELL"),
        ("O’Neill", "ONEILL"),
        ("Feasterville-Trevose", "FEASTERVILLE TREVOSE"),
        ("Mc Graw", "MCGRAW"),
        ("St. Louis", "SAINT LOUIS"),
        ("Ft Worth", "FORT WORTH"),
        ("Mt Jackson", "MOUNT JACKSON"),
        ("Stuckey’s", "STUCKEYS"),
    ],
)
def test_normalize_name(raw, expected):
    assert normalize_name(raw) == expected


def test_name_key_drops_spaces_so_spelling_variants_meet():
    assert name_key("De Witt") == name_key("DeWitt") == "DEWITT"


@pytest.mark.parametrize(
    ("name", "lsad", "expected"),
    [
        ("Big Cabin town", "43", "Big Cabin"),
        ("Dodge City city", "25", "Dodge City"),
        ("Abanda CDP", "57", "Abanda"),
        ("Bantam borough", "21", "Bantam"),
        ("Juneau city and borough", "53", "Juneau"),
        ("Indianapolis city (balance)", "00", "Indianapolis"),
        ("Lexington-Fayette urban county", "UC", "Lexington-Fayette"),
        ("Ranson corporation", "CN", "Ranson"),
    ],
)
def test_strip_gazetteer_suffix_uses_lsad_not_pattern(name, lsad, expected):
    assert strip_gazetteer_suffix(name, lsad) == expected
