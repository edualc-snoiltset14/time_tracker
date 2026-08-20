"""Tests for :func:`sum_even_numbers.sum_even_numbers`."""

import pytest

from sum_even_numbers import sum_even_numbers


class TestValidInput:
    """Cases the function is expected to sum successfully."""

    @pytest.mark.parametrize(
        ("numbers", "expected"),
        [
            pytest.param([1, 2, 3, 4, 5, 6], 12, id="mixed"),
            pytest.param([2, 4, 6], 12, id="all-even"),
            pytest.param([1, 3, 5], 0, id="all-odd"),
            pytest.param([], 0, id="empty"),
            pytest.param([0], 0, id="zero-is-even"),
            pytest.param([7], 0, id="single-odd"),
            pytest.param([8], 8, id="single-even"),
            pytest.param([-2, -3, -4], -6, id="negative-evens"),
            pytest.param([-1, 0, 1], 0, id="spanning-zero"),
            pytest.param([2, 2, 2], 6, id="duplicates-all-counted"),
        ],
    )
    def test_sums_even_values(self, numbers, expected):
        assert sum_even_numbers(numbers) == expected

    def test_does_not_mutate_input(self):
        numbers = [1, 2, 3, 4]
        original = list(numbers)
        sum_even_numbers(numbers)
        assert numbers == original

    def test_handles_large_integers(self):
        big = 10**30
        assert sum_even_numbers([big, big + 1]) == big


class TestIterableTypes:
    """Any iterable of integers is accepted, not just lists."""

    @pytest.mark.parametrize(
        ("numbers", "expected"),
        [
            pytest.param((1, 2, 3, 4), 6, id="tuple"),
            pytest.param({1, 2, 3, 4}, 6, id="set"),
            pytest.param(range(1, 7), 12, id="range"),
            pytest.param(frozenset({2, 5, 8}), 10, id="frozenset"),
        ],
    )
    def test_accepts_other_iterables(self, numbers, expected):
        assert sum_even_numbers(numbers) == expected

    def test_accepts_generator(self):
        assert sum_even_numbers(n for n in range(10)) == 20

    def test_consumes_single_pass_iterator_exactly_once(self):
        iterator = iter([1, 2, 3, 4])
        assert sum_even_numbers(iterator) == 6
        assert list(iterator) == [], "iterator should be fully consumed"

    def test_dict_iterates_over_keys(self):
        # Documenting the consequence of accepting any iterable: a dict
        # yields its keys, so only the keys are considered.
        assert sum_even_numbers({2: "a", 3: "b", 4: "c"}) == 6


class TestNonIterableInput:
    """``numbers`` itself must be iterable."""

    @pytest.mark.parametrize(
        ("value", "type_name"),
        [
            pytest.param(42, "int", id="int"),
            pytest.param(None, "NoneType", id="none"),
            pytest.param(3.5, "float", id="float"),
            pytest.param(object(), "object", id="object"),
        ],
    )
    def test_rejects_non_iterable(self, value, type_name):
        with pytest.raises(TypeError) as excinfo:
            sum_even_numbers(value)
        message = str(excinfo.value)
        assert "Expected an iterable of integers" in message
        assert type_name in message

    def test_non_iterable_error_has_no_confusing_cause(self):
        # Raised with ``from None``, so the internal ``iter()`` failure is
        # marked suppressed and the traceback shows only the descriptive
        # error rather than a "During handling ..." chain.
        with pytest.raises(TypeError) as excinfo:
            sum_even_numbers(42)
        assert excinfo.value.__cause__ is None
        assert excinfo.value.__suppress_context__ is True


class TestNonIntegerElements:
    """Every element must be a genuine, non-boolean integer."""

    @pytest.mark.parametrize(
        ("numbers", "index", "type_name"),
        [
            pytest.param([1, 2, "3", 4], 2, "str", id="str-element"),
            pytest.param([1, 2.5, 3], 1, "float", id="float-element"),
            pytest.param([2.0], 0, "float", id="even-valued-float"),
            pytest.param([1, None, 3], 1, "NoneType", id="none-element"),
            pytest.param([1, [2], 3], 1, "list", id="list-element"),
            pytest.param([2, 4, 6, "8"], 3, "str", id="last-element"),
        ],
    )
    def test_rejects_non_integer_element(self, numbers, index, type_name):
        with pytest.raises(TypeError) as excinfo:
            sum_even_numbers(numbers)
        message = str(excinfo.value)
        assert f"Non-integer value at index {index}" in message
        assert type_name in message

    @pytest.mark.parametrize(
        ("value", "index"),
        [
            pytest.param(True, 1, id="true"),
            pytest.param(False, 1, id="false"),
        ],
    )
    def test_rejects_booleans_despite_being_int_subclass(self, value, index):
        with pytest.raises(TypeError) as excinfo:
            sum_even_numbers([1, value, 3])
        message = str(excinfo.value)
        assert f"Non-integer value at index {index}" in message
        assert "bool" in message

    def test_string_input_rejects_its_first_character(self):
        # A string is iterable, so it is not caught as "non-iterable";
        # it fails on its first character instead.
        with pytest.raises(TypeError) as excinfo:
            sum_even_numbers("123")
        assert "Non-integer value at index 0" in str(excinfo.value)

    def test_error_message_includes_the_offending_value(self):
        with pytest.raises(TypeError) as excinfo:
            sum_even_numbers([1, "oops"])
        assert "'oops'" in str(excinfo.value)

    def test_rejects_before_consuming_rest_of_iterator(self):
        # Validation is eager: iteration stops at the first bad element.
        iterator = iter([2, "bad", 4])
        with pytest.raises(TypeError):
            sum_even_numbers(iterator)
        assert list(iterator) == [4]
