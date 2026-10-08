import slug


def test_punctuation_and_case():
    assert slug.slugify("Hello, World!") == "hello-world"


def test_underscores_and_spaces():
    assert slug.slugify("  A__b  ") == "a-b"


def test_empty():
    assert slug.slugify("") == ""
    assert slug.slugify("   ") == ""
    assert slug.slugify("---") == ""


def test_slash_and_accent():
    assert slug.slugify("A/B") == "ab"
    assert slug.slugify("Café") == "caf"


def test_already_a_slug():
    assert slug.slugify("already-slugged") == "already-slugged"
