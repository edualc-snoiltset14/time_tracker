def sum_even_numbers(numbers):
    """Return the sum of only the even integers in a list.

    Args:
        numbers: An iterable of integers.

    Returns:
        The sum of the integers that are even. Returns 0 if there are none.

    Raises:
        TypeError: If ``numbers`` is not iterable, or if any element is not
            an integer. Booleans are rejected because they are not meaningful
            values to sum here, even though ``bool`` is a subclass of ``int``.
    """
    try:
        iterator = iter(numbers)
    except TypeError:
        raise TypeError(
            f"Expected an iterable of integers, got {type(numbers).__name__}"
        )

    total = 0
    for index, value in enumerate(iterator):
        if isinstance(value, bool) or not isinstance(value, int):
            raise TypeError(
                f"Non-integer value at index {index}: "
                f"{value!r} ({type(value).__name__})"
            )
        if value % 2 == 0:
            total += value
    return total


if __name__ == "__main__":
    example = [1, 2, 3, 4, 5, 6]
    print(f"Sum of even numbers in {example}: {sum_even_numbers(example)}")

    # Invalid inputs are rejected with a clear error message.
    for bad in ([1, 2, "3", 4], [1, 2.5, 3], 42, [1, True, 3]):
        try:
            sum_even_numbers(bad)
        except TypeError as exc:
            print(f"Rejected {bad!r}: {exc}")
