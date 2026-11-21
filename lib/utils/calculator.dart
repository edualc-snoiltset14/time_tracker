// lib/utils/calculator.dart

/// The logic behind a basic four-function calculator, kept free of Flutter
/// so it can be unit tested on its own.
///
/// Feed it one key at a time through [press] and read [display] (the number
/// being entered or the last result) and [expression] (the pending operation).
class Calculator {
  static const String add = '+';
  static const String subtract = '−';
  static const String multiply = '×';
  static const String divide = '÷';
  static const String equals = '=';
  static const String clear = 'C';
  static const String negate = '±';
  static const String percent = '%';
  static const String backspace = '⌫';
  static const String decimal = '.';

  static const String errorText = 'Error';
  static const int _maxDigits = 15;
  static const Set<String> _operators = {add, subtract, multiply, divide};

  String _display = '0';
  double? _accumulator;
  String? _operator;

  /// True when the next digit starts a new number instead of extending the
  /// one on the display (after an operator, a result, or a reset).
  bool _startNewEntry = true;

  /// True right after an operator key, until the right operand is touched.
  /// Lets a second operator key swap the operator instead of evaluating.
  bool _awaitingOperand = false;

  String get display => _display;

  /// The pending left operand and operator, e.g. `12 ×`. Empty when idle.
  String get expression =>
      _operator == null ? '' : '${_format(_accumulator!)} $_operator';

  bool get hasError => _display == errorText;

  void press(String key) {
    if (hasError) {
      // Only a fresh number or a clear gets out of the error state.
      final startsNumber = _isDigit(key) || key == decimal;
      if (!startsNumber && key != clear) return;
      _reset();
    }

    if (_isDigit(key)) {
      _enterDigit(key);
    } else if (key == decimal) {
      _enterDecimal();
    } else if (_operators.contains(key)) {
      _enterOperator(key);
    } else if (key == equals) {
      _evaluate();
    } else if (key == clear) {
      _reset();
    } else if (key == negate) {
      _negate();
    } else if (key == percent) {
      _awaitingOperand = false;
      _setValue(_value / 100);
    } else if (key == backspace) {
      _deleteLast();
    }
  }

  double get _value => double.parse(_display);

  bool _isDigit(String key) =>
      key.length == 1 && key.codeUnitAt(0) >= 0x30 && key.codeUnitAt(0) <= 0x39;

  void _enterDigit(String digit) {
    _awaitingOperand = false;
    if (_startNewEntry) {
      _display = digit;
      _startNewEntry = false;
    } else if (_display == '0') {
      _display = digit;
    } else if (_display.replaceAll(RegExp(r'[-.]'), '').length < _maxDigits) {
      _display += digit;
    }
  }

  void _enterDecimal() {
    _awaitingOperand = false;
    if (_startNewEntry) {
      _display = '0.';
      _startNewEntry = false;
    } else if (!_display.contains(decimal)) {
      _display += decimal;
    }
  }

  /// Flips the sign on the text itself so a number that is still being
  /// typed keeps its exact digits and stays editable.
  void _negate() {
    if (_value == 0) return;
    _awaitingOperand = false;
    _display = _display.startsWith('-') ? _display.substring(1) : '-$_display';
  }

  void _enterOperator(String op) {
    // Chained input like `2 + 3 ×` evaluates the pending `2 + 3` first.
    // Pressing two operators in a row just swaps the operator.
    if (_operator != null && !_awaitingOperand) {
      if (!_evaluate()) return;
    }
    _accumulator = _value;
    _operator = op;
    _startNewEntry = true;
    _awaitingOperand = true;
  }

  /// Applies the pending operator. Returns false if it ended in an error.
  bool _evaluate() {
    final op = _operator;
    _awaitingOperand = false;
    if (op == null) {
      _startNewEntry = true;
      return true;
    }
    final a = _accumulator!;
    final b = _value;
    _operator = null;
    _accumulator = null;

    if (op == divide && b == 0) {
      _display = errorText;
      _startNewEntry = true;
      return false;
    }
    final result = switch (op) {
      add => a + b,
      subtract => a - b,
      multiply => a * b,
      _ => a / b,
    };
    if (!result.isFinite) {
      _display = errorText;
      _startNewEntry = true;
      return false;
    }
    _setValue(result);
    return true;
  }

  void _deleteLast() {
    if (_startNewEntry) return; // Results aren't editable.
    _display = _display.substring(0, _display.length - 1);
    if (_display.isEmpty || _display == '-') _display = '0';
  }

  void _reset() {
    _display = '0';
    _accumulator = null;
    _operator = null;
    _startNewEntry = true;
    _awaitingOperand = false;
  }

  void _setValue(double value) {
    _display = _format(value);
    _startNewEntry = true;
  }

  /// Formats without floating point noise (0.1 + 0.2 shows as 0.3) and
  /// without a trailing `.0` on whole numbers.
  static String _format(double value) {
    if (value == 0) return '0'; // Also normalises -0.0.
    final abs = value.abs();
    if (abs >= 1e15 || abs < 1e-9) {
      return value
          .toStringAsExponential(6)
          .replaceFirst(RegExp(r'\.?0+e'), 'e')
          .replaceFirst('e+', 'e');
    }
    if (value == value.truncateToDouble()) return value.toStringAsFixed(0);
    // Keep about 15 significant digits, the most a double holds reliably.
    final integerDigits = abs.truncate().toString().length;
    final decimals = (15 - integerDigits).clamp(0, 10);
    return value
        .toStringAsFixed(decimals)
        .replaceFirst(RegExp(r'\.?0+$'), '');
  }
}
