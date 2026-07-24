"""Utility for summing even numbers from a list."""

from typing import Iterable


def sum_even_numbers(numbers: Iterable[float]) -> float:
    """Return the sum of only the even numbers in the given list.

    Args:
        numbers: An iterable of numbers (ints or floats).

    Returns:
        The sum of all even numbers. Returns 0 if there are none.
    """
    return sum(n for n in numbers if n % 2 == 0)


if __name__ == "__main__":
    print(sum_even_numbers([1, 2, 3, 4, 5, 6]))  # 12
