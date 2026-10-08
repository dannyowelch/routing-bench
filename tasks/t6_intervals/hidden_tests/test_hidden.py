import pytest

import intervals


def test_gap_stays_open():
    assert intervals.merge([(1, 2), (3, 4)]) == [(1, 2), (3, 4)]


def test_point_unsorted_and_nested():
    assert intervals.merge([(5, 5), (1, 10), (2, 3), (1, 10)]) == [(1, 10)]


def test_negatives():
    assert intervals.merge([(-1, 0), (-2, -1)]) == [(-2, 0)]


def test_coverage():
    assert intervals.coverage([]) == 0
    assert intervals.coverage([(5, 5)]) == 1
    assert intervals.coverage([(1, 2), (2, 4)]) == 4
    assert intervals.coverage([(1, 2), (4, 4)]) == 3


def test_invalid():
    with pytest.raises(ValueError):
        intervals.merge([(1, 1), (3, 2)])
