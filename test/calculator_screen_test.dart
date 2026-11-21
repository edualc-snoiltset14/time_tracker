import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:time_tracker/screens/calculator/calculator_screen.dart';

void main() {
  const sizes = [Size(320, 480), Size(360, 640), Size(1280, 800)];

  for (final size in sizes) {
    testWidgets('lays out and computes at $size', (tester) async {
      tester.view.physicalSize = size;
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.reset);

      await tester.pumpWidget(
        MaterialApp(theme: ThemeData.dark(), home: const CalculatorScreen()),
      );

      String shown() => tester
          .widget<Text>(find.byKey(const Key('calculator_display')))
          .data!;

      // On-screen buttons.
      for (final key in ['7', '×', '6', '=']) {
        await tester.tap(find.widgetWithText(FilledButton, key));
        await tester.pump();
      }
      expect(shown(), '42');

      // Physical keyboard.
      await tester.sendKeyEvent(LogicalKeyboardKey.digit8, character: '8');
      await tester.sendKeyEvent(LogicalKeyboardKey.slash, character: '/');
      await tester.sendKeyEvent(LogicalKeyboardKey.digit2, character: '2');
      await tester.sendKeyEvent(LogicalKeyboardKey.enter);
      await tester.pump();
      expect(shown(), '4');

      // No layout overflow at this size.
      expect(tester.takeException(), isNull);
    });
  }
}
