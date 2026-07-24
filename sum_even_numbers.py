"""Utility for summing even numbers from a list."""

from numbers import Integral
from typing import Iterable


def sum_even_numbers(numbers: Iterable[int]) -> int:
    """Return the sum of only the even numbers in the given list.

    Args:
        numbers: An iterable of integers.

    Returns:
        The sum of all even numbers. Returns 0 if there are none.

    Raises:
        TypeError: If ``numbers`` is not iterable, or if any element is not
            an integer (e.g. a string, float, or ``None``). Note that
            booleans are rejected even though they subclass ``int``.
    """
    try:
        iterator = iter(numbers)
    except TypeError:
        raise TypeError(
            f"Expected an iterable of integers, got {type(numbers).__name__}"
        )

    total = 0
    for index, value in enumerate(iterator):
        if isinstance(value, bool) or not isinstance(value, Integral):
            raise TypeError(
                f"Element at index {index} is not an integer: "
                f"{value!r} ({type(value).__name__})"
            )
        if value % 2 == 0:
            total += value
    return total


if __name__ == "__main__":
    print(sum_even_numbers([1, 2, 3, 4, 5, 6]))  # 12
