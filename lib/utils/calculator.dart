// lib/utils/calculator.dart

/// Logic for a simple four-function calculator.
///
/// Feed it one key at a time through [press] and read [display] and
/// [expression] back. Keys: `0`-`9`, `.`, `+`, `-`, `×`, `÷`, `=`, `%`,
/// `±`, `⌫` (backspace) and `C` (clear).
class Calculator {
  static const String errorText = 'Error';
  static const int _maxDigits = 15;

  String _display = '0';
  double? _accumulator;
  String? _operator;

  /// True when the next digit starts a new number instead of extending the
  /// one on the display (after an operator, `=` or an error).
  bool _startNewEntry = true;

  /// The number currently shown.
  String get display => _display;

  /// The pending left-hand side and operator, e.g. `12 ×`, or empty.
  String get expression {
    final acc = _accumulator;
    if (acc == null || _operator == null) return '';
    return '${_format(acc)} $_operator';
  }

  bool get hasError => _display == errorText;

  void press(String key) {
    if (key == 'C') {
      _clear();
      return;
    }
    // After an error only a fresh number (or C) gets things going again.
    if (hasError) {
      if (!_isDigit(key) && key != '.') return;
      _clear();
    }

    if (_isDigit(key)) {
      _digit(key);
    } else if (key == '.') {
      _decimalPoint();
    } else if (key == '+' || key == '-' || key == '×' || key == '÷') {
      _setOperator(key);
    } else if (key == '=') {
      _equals();
    } else if (key == '%') {
      _show(double.parse(_display) / 100);
    } else if (key == '±') {
      _toggleSign();
    } else if (key == '⌫') {
      _backspace();
    }
  }

  bool _isDigit(String key) =>
      key.length == 1 && key.compareTo('0') >= 0 && key.compareTo('9') <= 0;

  void _clear() {
    _display = '0';
    _accumulator = null;
    _operator = null;
    _startNewEntry = true;
  }

  void _digit(String digit) {
    if (_startNewEntry) {
      _display = digit;
      _startNewEntry = false;
    } else if (_display == '0') {
      _display = digit;
    } else if (_display == '-0') {
      _display = '-$digit';
    } else if (_display.replaceAll(RegExp(r'[-.]'), '').length < _maxDigits) {
      _display += digit;
    }
  }

  void _decimalPoint() {
    if (_startNewEntry) {
      _display = '0.';
      _startNewEntry = false;
    } else if (!_display.contains('.')) {
      _display += '.';
    }
  }

  void _setOperator(String op) {
    // Chained input such as "2 + 3 ×" evaluates "2 + 3" first. Pressing two
    // operators in a row just replaces the pending one.
    if (_operator != null && !_startNewEntry) {
      if (!_evaluate()) return;
    }
    _accumulator = double.parse(_display);
    _operator = op;
    _startNewEntry = true;
  }

  void _equals() {
    if (_operator == null) return;
    if (!_evaluate()) return;
    _accumulator = null;
    _operator = null;
  }

  /// Applies the pending operator to the accumulator and the display.
  /// Returns false if the result is not a finite number.
  bool _evaluate() {
    final left = _accumulator!;
    final right = double.parse(_display);
    final double result;
    switch (_operator) {
      case '+':
        result = left + right;
        break;
      case '-':
        result = left - right;
        break;
      case '×':
        result = left * right;
        break;
      default:
        result = left / right;
    }
    return _show(result);
  }

  bool _show(double value) {
    _startNewEntry = true;
    if (value.isNaN || value.isInfinite) {
      _accumulator = null;
      _operator = null;
      _display = errorText;
      return false;
    }
    _display = _format(value);
    return true;
  }

  void _toggleSign() {
    if (double.parse(_display) == 0) return;
    _display =
        _display.startsWith('-') ? _display.substring(1) : '-$_display';
  }

  void _backspace() {
    if (_startNewEntry) return;
    _display = _display.substring(0, _display.length - 1);
    if (_display.isEmpty || _display == '-') _display = '0';
  }

  static String _format(double value) {
    // Round to 12 significant digits so 0.1 + 0.2 shows 0.3.
    final rounded = double.parse(value.toStringAsPrecision(12));
    if (rounded == rounded.truncateToDouble() && rounded.abs() < 1e15) {
      return rounded.toInt().toString();
    }
    return rounded.toString();
  }
}
