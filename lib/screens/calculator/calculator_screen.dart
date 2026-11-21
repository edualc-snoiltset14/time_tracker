// lib/screens/calculator/calculator_screen.dart
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:time_tracker/utils/calculator.dart';

class CalculatorScreen extends StatefulWidget {
  const CalculatorScreen({super.key});

  @override
  State<CalculatorScreen> createState() => _CalculatorScreenState();
}

class _CalculatorScreenState extends State<CalculatorScreen> {
  static const List<List<String>> _rows = [
    ['C', '⌫', '%', '÷'],
    ['7', '8', '9', '×'],
    ['4', '5', '6', '-'],
    ['1', '2', '3', '+'],
    ['±', '0', '.', '='],
  ];

  static const Set<String> _operatorKeys = {'÷', '×', '-', '+', '='};
  static const Set<String> _functionKeys = {'C', '⌫', '%'};

  final Calculator _calculator = Calculator();

  void _press(String key) {
    setState(() => _calculator.press(key));
  }

  /// Lets the calculator be driven from a physical keyboard.
  KeyEventResult _onKeyEvent(FocusNode node, KeyEvent event) {
    if (event is KeyUpEvent) return KeyEventResult.ignored;

    final logicalKey = event.logicalKey;
    String? key;
    if (logicalKey == LogicalKeyboardKey.enter ||
        logicalKey == LogicalKeyboardKey.numpadEnter) {
      key = '=';
    } else if (logicalKey == LogicalKeyboardKey.backspace) {
      key = '⌫';
    } else if (logicalKey == LogicalKeyboardKey.delete) {
      key = 'C';
    } else {
      final character = event.character;
      if (character == '*') {
        key = '×';
      } else if (character == '/') {
        key = '÷';
      } else if (character == ',') {
        key = '.';
      } else if (character == 'c' || character == 'C') {
        key = 'C';
      } else if (character != null && '0123456789.+-=%'.contains(character)) {
        key = character;
      }
    }

    if (key == null) return KeyEventResult.ignored;
    _press(key);
    return KeyEventResult.handled;
  }

  @override
  Widget build(BuildContext context) {
    final colors = Theme.of(context).colorScheme;

    return Scaffold(
      appBar: AppBar(title: const Text('Calculator')),
      body: Focus(
        autofocus: true,
        onKeyEvent: _onKeyEvent,
        child: SafeArea(
          child: Center(
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 420, maxHeight: 720),
              child: Padding(
                padding: const EdgeInsets.all(16),
                child: Column(
                  children: [
                    Expanded(flex: 2, child: _buildDisplay(colors)),
                    const SizedBox(height: 8),
                    for (final row in _rows)
                      Expanded(
                        child: Row(
                          children: [
                            for (final key in row)
                              Expanded(child: _buildButton(key, colors)),
                          ],
                        ),
                      ),
                  ],
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildDisplay(ColorScheme colors) {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 8),
      child: Column(
        mainAxisAlignment: MainAxisAlignment.end,
        crossAxisAlignment: CrossAxisAlignment.end,
        children: [
          Text(
            _calculator.expression,
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: TextStyle(fontSize: 20, color: colors.onSurfaceVariant),
          ),
          const SizedBox(height: 4),
          // Flexible so the number shrinks on short windows as well as for
          // long values.
          Flexible(
            child: FittedBox(
              fit: BoxFit.scaleDown,
              alignment: Alignment.centerRight,
              child: Text(
                _calculator.display,
                key: const Key('calculator_display'),
                maxLines: 1,
                style: TextStyle(
                  fontSize: 56,
                  fontWeight: FontWeight.w300,
                  color:
                      _calculator.hasError ? colors.error : colors.onSurface,
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildButton(String key, ColorScheme colors) {
    final Color background;
    final Color foreground;
    if (key == '=') {
      background = colors.primary;
      foreground = colors.onPrimary;
    } else if (_operatorKeys.contains(key)) {
      background = colors.primaryContainer;
      foreground = colors.onPrimaryContainer;
    } else if (_functionKeys.contains(key)) {
      background = colors.secondaryContainer;
      foreground = colors.onSecondaryContainer;
    } else {
      background = colors.surfaceContainerHighest;
      foreground = colors.onSurface;
    }

    return Padding(
      padding: const EdgeInsets.all(4),
      child: SizedBox.expand(
        child: FilledButton(
          onPressed: () => _press(key),
          style: FilledButton.styleFrom(
            backgroundColor: background,
            foregroundColor: foreground,
            padding: EdgeInsets.zero,
            shape: RoundedRectangleBorder(
              borderRadius: BorderRadius.circular(16),
            ),
            textStyle: const TextStyle(fontSize: 24),
          ),
          child: key == '⌫'
              ? const Icon(Icons.backspace_outlined, size: 24)
              : Text(key == '-' ? '−' : key),
        ),
      ),
    );
  }
}
