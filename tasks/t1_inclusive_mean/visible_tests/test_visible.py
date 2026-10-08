import stats


def test_two_elements():
    assert stats.mean_inclusive([10, 20, 30, 40], 1, 2) == 25
