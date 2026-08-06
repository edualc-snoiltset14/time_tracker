def sum_even_numbers(numbers):
    """Return the sum of the even numbers in the given list.

    Args:
        numbers: A list (or any iterable) of integers.

    Returns:
        The sum of all even numbers in the list. Returns 0 if the
        list is empty or contains no even numbers.

    Raises:
        TypeError: If ``numbers`` is not iterable, or if it contains
            a value that is not an integer (e.g. str, float, bool, None).
    """
    try:
        items = iter(numbers)
    except TypeError:
        raise TypeError(
            f"expected a list of integers, got {type(numbers).__name__}"
        ) from None

    total = 0
    for index, value in enumerate(items):
        # bool is a subclass of int, but True/False are not valid inputs here
        if isinstance(value, bool) or not isinstance(value, int):
            raise TypeError(
                f"all values must be integers; "
                f"got {type(value).__name__} ({value!r}) at index {index}"
            )
        if value % 2 == 0:
            total += value
    return total


if __name__ == "__main__":
    print(sum_even_numbers([1, 2, 3, 4, 5, 6]))  # 12
    print(sum_even_numbers([-2, -1, 0, 7]))      # -2
    print(sum_even_numbers([]))                  # 0

    for bad_input in ([1, 2, "3"], [1, 2.5], [1, None], [True, 2], 42):
        try:
            sum_even_numbers(bad_input)
        except TypeError as error:
            print(f"{bad_input!r}: TypeError: {error}")
