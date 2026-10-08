import pytest

import stats


def test_single_element():
    assert stats.mean_inclusive([5], 0, 0) == 5


def test_full_range():
    assert stats.mean_inclusive([1, 2, 3], 0, 2) == 2


def test_negatives():
    assert stats.mean_inclusive([-4, -2], 0, 1) == -3


def test_start_after_end():
    with pytest.raises(ValueError):
        stats.mean_inclusive([1, 2, 3], 2, 1)


def test_index_too_high():
    with pytest.raises(IndexError):
        stats.mean_inclusive([1, 2, 3], 0, 3)


def test_negative_index():
    with pytest.raises(IndexError):
        stats.mean_inclusive([1, 2, 3], -1, 1)
