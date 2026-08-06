def sum_even_numbers(numbers):
    """Return the sum of the even numbers in the given list.

    Args:
        numbers: A list of numbers (ints or floats).

    Returns:
        The sum of all even numbers in the list. Returns 0 if the list
        is empty or contains no even numbers.
    """
    return sum(n for n in numbers if n % 2 == 0)


if __name__ == "__main__":
    print(sum_even_numbers([1, 2, 3, 4, 5, 6]))  # 12
    print(sum_even_numbers([1, 3, 5]))           # 0
    print(sum_even_numbers([]))                  # 0
    print(sum_even_numbers([-2, -1, 0, 7, 8]))   # 6
