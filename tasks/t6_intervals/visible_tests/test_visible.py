import intervals


def test_touching_endpoints_merge():
    assert intervals.merge([(1, 2), (2, 5)]) == [(1, 5)]
