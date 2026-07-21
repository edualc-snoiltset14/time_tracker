def sum_even_numbers(numbers):
    """Return the sum of only the even numbers in a list.

    Args:
        numbers: An iterable of numbers (ints or floats).

    Returns:
        The sum of the numbers that are even. Returns 0 if there are none.
    """
    return sum(n for n in numbers if n % 2 == 0)


if __name__ == "__main__":
    example = [1, 2, 3, 4, 5, 6]
    print(f"Sum of even numbers in {example}: {sum_even_numbers(example)}")
