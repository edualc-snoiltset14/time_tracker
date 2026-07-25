/// Tower of Hanoi solver.
///
/// Move a stack of [n] disks from a source peg to a target peg using an
/// auxiliary peg, following the rules:
///   1. Only one disk may be moved at a time.
///   2. A larger disk may never be placed on top of a smaller disk.
///
/// The minimum number of moves required is 2^n - 1.

/// Represents a single move of a disk from one peg to another.
class HanoiMove {
  final int disk;
  final String from;
  final String to;

  const HanoiMove(this.disk, this.from, this.to);

  @override
  String toString() => 'Move disk $disk from $from to $to';
}

/// Returns the ordered list of moves that solves the Tower of Hanoi puzzle
/// for [n] disks.
///
/// Throws [ArgumentError] if [n] is negative.
List<HanoiMove> solveHanoi(
  int n, {
  String source = 'A',
  String target = 'C',
  String auxiliary = 'B',
}) {
  if (n < 0) {
    throw ArgumentError.value(n, 'n', 'must be non-negative');
  }
  final moves = <HanoiMove>[];
  _hanoi(n, source, target, auxiliary, moves);
  return moves;
}

void _hanoi(
  int n,
  String source,
  String target,
  String auxiliary,
  List<HanoiMove> moves,
) {
  if (n == 0) return;
  // Move the top n-1 disks out of the way onto the auxiliary peg.
  _hanoi(n - 1, source, auxiliary, target, moves);
  // Move the largest remaining disk to the target peg.
  moves.add(HanoiMove(n, source, target));
  // Move the n-1 disks from auxiliary onto the target peg.
  _hanoi(n - 1, auxiliary, target, source, moves);
}

void main() {
  const disks = 3;
  final moves = solveHanoi(disks);
  print('Solving Tower of Hanoi for $disks disks '
      '(${moves.length} moves):');
  for (final move in moves) {
    print(move);
  }
}
