import slug


def test_words():
    assert slug.slugify("Hello World") == "hello-world"
