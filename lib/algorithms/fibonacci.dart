/// Fibonacci sequence utilities.
///
/// The Fibonacci sequence is defined as:
///   F(0) = 0
///   F(1) = 1
///   F(n) = F(n-1) + F(n-2)  for n >= 2

/// Returns the nth Fibonacci number using an efficient iterative approach.
///
/// Runs in O(n) time and O(1) space.
/// Throws [ArgumentError] if [n] is negative.
int fibonacci(int n) {
  if (n < 0) {
    throw ArgumentError.value(n, 'n', 'must be non-negative');
  }
  if (n < 2) return n;

  var previous = 0;
  var current = 1;
  for (var i = 2; i <= n; i++) {
    final next = previous + current;
    previous = current;
    current = next;
  }
  return current;
}

/// Returns the first [count] Fibonacci numbers as a list.
///
/// Throws [ArgumentError] if [count] is negative.
List<int> fibonacciSequence(int count) {
  if (count < 0) {
    throw ArgumentError.value(count, 'count', 'must be non-negative');
  }
  final result = <int>[];
  var previous = 0;
  var current = 1;
  for (var i = 0; i < count; i++) {
    result.add(previous);
    final next = previous + current;
    previous = current;
    current = next;
  }
  return result;
}

void main() {
  const n = 10;
  print('fibonacci($n) = ${fibonacci(n)}');
  print('First $n Fibonacci numbers: ${fibonacciSequence(n)}');
}
