def sum_even_numbers(numbers):
    """Return the sum of the even numbers in the given list.

    Args:
        numbers: A list (or any iterable) of integers.

    Returns:
        The sum of the even numbers. Returns 0 if there are none.

    Raises:
        TypeError: If ``numbers`` is not iterable, or if any element is
            not an integer (bools are also rejected).

    Examples:
        >>> sum_even_numbers([1, 2, 3, 4, 5, 6])
        12
        >>> sum_even_numbers([1, 3, 5])
        0
        >>> sum_even_numbers([-2, -1, 0, 7])
        -2
        >>> sum_even_numbers([1, 2, "3"])
        Traceback (most recent call last):
            ...
        TypeError: expected an integer at index 2, got str: '3'
        >>> sum_even_numbers([2, 4.5])
        Traceback (most recent call last):
            ...
        TypeError: expected an integer at index 1, got float: 4.5
        >>> sum_even_numbers([True, 2])
        Traceback (most recent call last):
            ...
        TypeError: expected an integer at index 0, got bool: True
        >>> sum_even_numbers(42)
        Traceback (most recent call last):
            ...
        TypeError: expected an iterable of integers, got int
    """
    try:
        iterator = enumerate(numbers)
    except TypeError:
        raise TypeError(
            f"expected an iterable of integers, got {type(numbers).__name__}"
        ) from None

    total = 0
    for index, value in iterator:
        # bool is a subclass of int, so check for it explicitly
        if isinstance(value, bool) or not isinstance(value, int):
            raise TypeError(
                f"expected an integer at index {index}, "
                f"got {type(value).__name__}: {value!r}"
            )
        if value % 2 == 0:
            total += value
    return total


if __name__ == "__main__":
    import doctest

    doctest.testmod(verbose=True)
