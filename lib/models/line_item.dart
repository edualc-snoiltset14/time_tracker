// lib/models/line_item.dart
import 'dart:convert';

class LineItem {
  final String description;
  final double quantity; // Represents hours
  final double unitPrice; // Represents hourly rate

  LineItem({
    required this.description,
    required this.quantity,
    required this.unitPrice,
  });

  double get total => quantity * unitPrice;

  // Methods to convert to/from JSON so we can save it in the database
  Map<String, dynamic> toJson() {
    return {
      'description': description,
      'quantity': quantity,
      'unitPrice': unitPrice,
    };
  }

  factory LineItem.fromJson(Map<String, dynamic> json) {
    final description = json['description'];
    if (description is! String) {
      throw FormatException(
        "Line item 'description' must be a string, but got "
        '${description.runtimeType}.',
      );
    }
    return LineItem(
      description: description,
      quantity: _parseNumber(json['quantity'], 'quantity'),
      unitPrice: _parseNumber(json['unitPrice'], 'unitPrice'),
    );
  }

  // Validates that [value] is numeric and returns it as a double. Throws a
  // FormatException naming the offending field and value when it is not,
  // instead of letting an opaque cast error propagate to the caller.
  static double _parseNumber(dynamic value, String field) {
    if (value is num) {
      return value.toDouble();
    }
    final shown = value is String ? '"$value"' : value;
    throw FormatException(
      "Line item '$field' must be a number, but got $shown "
      '(${value.runtimeType}).',
    );
  }
}

// Helper functions to encode/decode a list of items
String lineItemsToJson(List<LineItem> items) {
  return jsonEncode(items.map((item) => item.toJson()).toList());
}

List<LineItem> lineItemsFromJson(String jsonString) {
  final dynamic decoded = jsonDecode(jsonString);
  if (decoded is! List) {
    throw FormatException(
      'Expected a JSON list of line items, but got ${decoded.runtimeType}.',
    );
  }
  final items = <LineItem>[];
  for (var i = 0; i < decoded.length; i++) {
    final element = decoded[i];
    if (element is! Map<String, dynamic>) {
      throw FormatException(
        'Line item at index $i must be a JSON object, but got '
        '${element.runtimeType}.',
      );
    }
    try {
      items.add(LineItem.fromJson(element));
    } on FormatException catch (e) {
      throw FormatException('Invalid line item at index $i: ${e.message}');
    }
  }
  return items;
}
