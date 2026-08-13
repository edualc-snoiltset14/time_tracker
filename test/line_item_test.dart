import 'package:flutter_test/flutter_test.dart';
import 'package:time_tracker/models/line_item.dart';

void main() {
  group('lineItemsFromJson', () {
    test('parses a list of valid numeric line items', () {
      const json =
          '[{"description":"Design","quantity":2,"unitPrice":50.0}]';
      final items = lineItemsFromJson(json);
      expect(items, hasLength(1));
      expect(items.first.quantity, 2.0);
      expect(items.first.unitPrice, 50.0);
      expect(items.first.total, 100.0);
    });

    test('throws FormatException when a quantity is a non-numeric string', () {
      const json =
          '[{"description":"Design","quantity":"two","unitPrice":50.0}]';
      expect(() => lineItemsFromJson(json), throwsFormatException);
    });

    test('error names the offending index and field', () {
      const json =
          '[{"description":"A","quantity":1,"unitPrice":10},'
          '{"description":"B","quantity":"oops","unitPrice":10}]';
      expect(
        () => lineItemsFromJson(json),
        throwsA(
          isA<FormatException>().having(
            (e) => e.message,
            'message',
            allOf(contains('index 1'), contains('quantity')),
          ),
        ),
      );
    });

    test('throws when a list element is not a JSON object', () {
      expect(() => lineItemsFromJson('[42]'), throwsFormatException);
    });

    test('throws when the top-level JSON is not a list', () {
      const json = '{"description":"A","quantity":1,"unitPrice":2}';
      expect(() => lineItemsFromJson(json), throwsFormatException);
    });
  });
}
