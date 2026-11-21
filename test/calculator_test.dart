import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:time_tracker/screens/calculator/calculator_screen.dart';
import 'package:time_tracker/utils/calculator.dart';

/// Presses each space-separated key and returns the resulting display.
String run(String keys) {
  final calculator = Calculator();
  for (final key in keys.split(' ')) {
    calculator.press(key);
  }
  return calculator.display;
}

void main() {
  group('Calculator', () {
    test('starts at zero', () {
      expect(Calculator().display, '0');
      expect(Calculator().expression, '');
    });

    test('basic arithmetic', () {
      expect(run('1 2 + 3 ='), '15');
      expect(run('9 − 1 2 ='), '-3');
      expect(run('6 × 7 ='), '42');
      expect(run('1 ÷ 4 ='), '0.25');
    });

    test('chained operators evaluate left to right', () {
      expect(run('2 + 3 ×'), '5');
      expect(run('2 + 3 × 4 ='), '20');
    });

    test('a second operator replaces the first', () {
      expect(run('8 + − 3 ='), '5');
    });

    test('continues from a result', () {
      expect(run('2 + 3 = × 4 ='), '20');
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

    test('negate', () {
      expect(run('5 ±'), '-5');
      expect(run('5 ± ±'), '5');
      expect(run('0 ±'), '0');
      expect(run('5 ± 2'), '-52');
      expect(run('8 + 3 ± ='), '5');
    });

    test('percent', () {
      expect(run('5 0 %'), '0.5');
      expect(run('2 0 0 × 1 0 % ='), '20');
      expect(run('2 0 0 + 1 0 % −'), '200.1');
    });

    test('backspace edits the entry but not a result', () {
      expect(run('1 2 3 ⌫'), '12');
      expect(run('7 ⌫'), '0');
      expect(run('5 ± ⌫'), '0');
      expect(run('1 2 + 3 = ⌫'), '15');
    });

    test('clear resets everything', () {
      expect(run('1 2 + 3 C 4 ='), '4');
    });

    test('division by zero is an error until cleared or retyped', () {
      final calculator = Calculator();
      for (final key in ['5', '÷', '0', '=']) {
        calculator.press(key);
      }
      expect(calculator.display, Calculator.errorText);
      expect(calculator.hasError, isTrue);

      calculator.press('+');
      expect(calculator.hasError, isTrue);

      calculator.press('9');
      expect(calculator.display, '9');
      expect(run('5 ÷ 0 = C'), '0');
    });

    test('expression shows the pending operation', () {
      final calculator = Calculator();
      for (final key in ['1', '2', '×']) {
        calculator.press(key);
      }
      expect(calculator.expression, '12 ×');
      calculator.press('3');
      calculator.press('=');
      expect(calculator.expression, '');
    });

    test('entry is capped at 15 digits', () {
      expect(run(List.filled(20, '9').join(' ')), '9' * 15);
    });

    test('very large results use exponent notation', () {
      expect(run('${List.filled(15, '9').join(' ')} × 1 0 0 0 ='), '1e18');
    });
  });

  testWidgets('CalculatorScreen computes from button taps', (tester) async {
    await tester.pumpWidget(const MaterialApp(home: CalculatorScreen()));

    for (final key in ['7', '×', '6', '=']) {
      await tester.tap(find.byKey(ValueKey('calculator-key-$key')));
      await tester.pump();
    }

    final display = tester.widget<Text>(
      find.byKey(const ValueKey('calculator-display')),
    );
    expect(display.data, '42');
  });
}
