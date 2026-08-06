def sum_even_numbers(numbers):
    """Return the sum of the even numbers in the given list.

    Args:
        numbers: A list (or other iterable) of integers.

    Returns:
        The sum of all even numbers in the list. Returns 0 if the list
        is empty or contains no even numbers.

    Raises:
        TypeError: If ``numbers`` is not iterable, or if any element is
            not an integer (e.g. a float, string, None, or bool).
    """
    if not hasattr(numbers, "__iter__"):
        raise TypeError(
            f"Expected a list of integers, got {type(numbers).__name__}"
        )

    total = 0
    for index, value in enumerate(numbers):
        # bool is a subclass of int, but True/False aren't valid inputs here
        if isinstance(value, bool) or not isinstance(value, int):
            raise TypeError(
                f"All elements must be integers; element at index {index} "
                f"is {value!r} ({type(value).__name__})"
            )
        if value % 2 == 0:
            total += value

    return total


if __name__ == "__main__":
    print(sum_even_numbers([1, 2, 3, 4, 5, 6]))  # 12
    print(sum_even_numbers([1, 3, 5]))           # 0
    print(sum_even_numbers([]))                  # 0
    print(sum_even_numbers([-2, -1, 0, 7, 8]))   # 6

    # Invalid inputs now raise TypeError with a helpful message
    for bad_input in ([1, 2, "3"], [1, 2.5, 4], [1, None], [True, 2], 42):
        try:
            sum_even_numbers(bad_input)
        except TypeError as error:
            print(f"TypeError: {error}")
