import 'package:flutter_test/flutter_test.dart';
import 'package:time_tracker/utils/calculator.dart';

/// Presses each space-separated key in [keys] and returns the display.
String run(String keys) {
  final calculator = Calculator();
  for (final key in keys.split(' ')) {
    calculator.press(key);
  }
  return calculator.display;
}

void main() {
  test('starts at zero', () {
    expect(Calculator().display, '0');
  });

  test('basic arithmetic', () {
    expect(run('1 2 + 7 ='), '19');
    expect(run('9 - 1 0 ='), '-1');
    expect(run('6 × 7 ='), '42');
    expect(run('1 ÷ 4 ='), '0.25');
  });

  test('chained operators evaluate left to right', () {
    expect(run('2 + 3 × 4 ='), '20');
  });

  test('a second operator replaces the pending one', () {
    expect(run('8 + × 2 ='), '16');
  });

  test('result can be used in the next calculation', () {
    expect(run('2 + 3 = × 4 ='), '20');
  });

  test('typing after equals starts a new number', () {
    expect(run('2 + 3 = 7'), '7');
  });

  test('decimals', () {
    expect(run('. 5 + 1 . 2 5 ='), '1.75');
    expect(run('1 . . 5'), '1.5');
    expect(run('0 . 1 + 0 . 2 ='), '0.3');
  });

  test('leading zeros are dropped', () {
    expect(run('0 0 7'), '7');
  });

  test('percent and sign toggle', () {
    expect(run('5 0 %'), '0.5');
    expect(run('5 ±'), '-5');
    expect(run('5 ± ±'), '5');
    expect(run('±'), '0');
  });

  test('backspace', () {
    expect(run('1 2 3 ⌫'), '12');
    expect(run('5 ⌫'), '0');
    expect(run('5 ± ⌫'), '0');
    expect(run('2 + 3 = ⌫'), '5');
  });

  test('clear resets everything', () {
    final calculator = Calculator();
    for (final key in ['9', '×', '9', 'C']) {
      calculator.press(key);
    }
    expect(calculator.display, '0');
    expect(calculator.expression, '');
  });

  test('expression shows the pending operation', () {
    final calculator = Calculator();
    for (final key in ['1', '2', '×']) {
      calculator.press(key);
    }
    expect(calculator.expression, '12 ×');
  });

  test('division by zero shows an error and recovers', () {
    expect(run('5 ÷ 0 ='), Calculator.errorText);
    expect(run('5 ÷ 0 = + ='), Calculator.errorText);
    expect(run('5 ÷ 0 = 3 + 4 ='), '7');
    expect(run('5 ÷ 0 = C'), '0');
  });
}
