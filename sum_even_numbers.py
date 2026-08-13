def sum_even_numbers(numbers):
    """Return the sum of the even numbers in the given list.

    Args:
        numbers: A list (or any iterable) of numbers.

    Returns:
        The sum of the even numbers. Returns 0 if there are none.

    Examples:
        >>> sum_even_numbers([1, 2, 3, 4, 5, 6])
        12
        >>> sum_even_numbers([1, 3, 5])
        0
        >>> sum_even_numbers([-2, -1, 0, 7])
        -2
    """
    return sum(n for n in numbers if n % 2 == 0)


if __name__ == "__main__":
    import doctest

    doctest.testmod(verbose=True)
