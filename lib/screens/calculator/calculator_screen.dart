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
    [Calculator.clear, Calculator.negate, Calculator.percent, Calculator.divide],
    ['7', '8', '9', Calculator.multiply],
    ['4', '5', '6', Calculator.subtract],
    ['1', '2', '3', Calculator.add],
    [Calculator.backspace, '0', Calculator.decimal, Calculator.equals],
  ];

  static const Set<String> _operatorKeys = {
    Calculator.divide,
    Calculator.multiply,
    Calculator.subtract,
    Calculator.add,
    Calculator.equals,
  };

  static const Set<String> _functionKeys = {
    Calculator.clear,
    Calculator.negate,
    Calculator.percent,
    Calculator.backspace,
  };

  /// Physical keyboard characters that map onto a calculator key.
  static const Map<String, String> _characterKeys = {
    '+': Calculator.add,
    '-': Calculator.subtract,
    '*': Calculator.multiply,
    'x': Calculator.multiply,
    '/': Calculator.divide,
    '=': Calculator.equals,
    '%': Calculator.percent,
    '.': Calculator.decimal,
    ',': Calculator.decimal,
    'c': Calculator.clear,
  };

  final Calculator _calculator = Calculator();

  void _press(String key) {
    setState(() => _calculator.press(key));
  }

  KeyEventResult _onKeyEvent(FocusNode node, KeyEvent event) {
    if (event is KeyUpEvent) return KeyEventResult.ignored;

    final logicalKey = event.logicalKey;
    String? key;
    if (logicalKey == LogicalKeyboardKey.enter ||
        logicalKey == LogicalKeyboardKey.numpadEnter) {
      key = Calculator.equals;
    } else if (logicalKey == LogicalKeyboardKey.backspace) {
      key = Calculator.backspace;
    } else if (logicalKey == LogicalKeyboardKey.delete) {
      key = Calculator.clear;
    } else {
      final character = event.character?.toLowerCase();
      if (character != null) {
        key = RegExp(r'^[0-9]$').hasMatch(character)
            ? character
            : _characterKeys[character];
      }
    }

    if (key == null) return KeyEventResult.ignored;
    _press(key);
    return KeyEventResult.handled;
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

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
                    Expanded(
                      flex: 2,
                      child: _Display(
                        expression: _calculator.expression,
                        value: _calculator.display,
                        isError: _calculator.hasError,
                      ),
                    ),
                    const SizedBox(height: 16),
                    Expanded(
                      flex: 5,
                      child: Column(
                        children: [
                          for (final row in _rows)
                            Expanded(
                              child: Row(
                                children: [
                                  for (final key in row)
                                    Expanded(
                                      child: Padding(
                                        padding: const EdgeInsets.all(4),
                                        child: _buildButton(theme, key),
                                      ),
                                    ),
                                ],
                              ),
                            ),
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

  Widget _buildButton(ThemeData theme, String key) {
    final colors = theme.colorScheme;
    final Color background;
    final Color foreground;
    if (_operatorKeys.contains(key)) {
      background = Colors.deepPurple;
      foreground = Colors.white;
    } else if (_functionKeys.contains(key)) {
      background = colors.surfaceContainerHighest;
      foreground = Colors.tealAccent;
    } else {
      background = colors.surfaceContainerHigh;
      foreground = colors.onSurface;
    }

    return SizedBox.expand(
      child: FilledButton(
        key: ValueKey('calculator-key-$key'),
        onPressed: () => _press(key),
        style: FilledButton.styleFrom(
          backgroundColor: background,
          foregroundColor: foreground,
          padding: EdgeInsets.zero,
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(16),
          ),
          textStyle: const TextStyle(fontSize: 24, fontWeight: FontWeight.w500),
        ),
        child: key == Calculator.backspace
            ? const Icon(Icons.backspace_outlined, semanticLabel: 'Backspace')
            : Text(key),
      ),
    );
  }
}

class _Display extends StatelessWidget {
  const _Display({
    required this.expression,
    required this.value,
    required this.isError,
  });

  final String expression;
  final String value;
  final bool isError;

  @override
  Widget build(BuildContext context) {
    final colors = Theme.of(context).colorScheme;

    return Container(
      width: double.infinity,
      padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 12),
      decoration: BoxDecoration(
        color: Theme.of(context).cardColor,
        borderRadius: BorderRadius.circular(16),
      ),
      child: Column(
        mainAxisAlignment: MainAxisAlignment.end,
        crossAxisAlignment: CrossAxisAlignment.end,
        children: [
          Text(
            expression,
            key: const ValueKey('calculator-expression'),
            maxLines: 1,
            style: TextStyle(fontSize: 18, color: colors.onSurfaceVariant),
          ),
          const SizedBox(height: 4),
          // Long numbers shrink to fit rather than overflow.
          FittedBox(
            fit: BoxFit.scaleDown,
            alignment: Alignment.centerRight,
            child: Text(
              value,
              key: const ValueKey('calculator-display'),
              maxLines: 1,
              style: TextStyle(
                fontSize: 56,
                fontWeight: FontWeight.w300,
                color: isError ? colors.error : colors.onSurface,
              ),
            ),
          ),
        ],
      ),
    );
  }
}
