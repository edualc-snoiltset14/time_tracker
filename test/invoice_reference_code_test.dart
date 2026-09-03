// Covers the sequential reference codes generated for new invoices:
// the first invoice of a month, the next one in a month that already has
// invoices, and a code that gets claimed by someone else while the new-invoice
// screen sits open.
import 'package:drift/drift.dart' as drift;
import 'package:drift/native.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:time_tracker/database/database.dart';
import 'package:time_tracker/screens/invoices/invoice_edit_screen.dart';

void main() {
  late AppDatabase db;

  setUp(() {
    db = AppDatabase.forTesting(NativeDatabase.memory());
  });

  tearDown(() async {
    await db.close();
  });

  String prefixForThisMonth() {
    final now = DateTime.now();
    return 'INV-${now.year}-${now.month.toString().padLeft(2, '0')}-';
  }

  Future<int> insertClient(String name) {
    return db.into(db.clients).insert(ClientsCompanion(name: drift.Value(name)));
  }

  Future<void> insertInvoice(String reference, int clientId) async {
    await db.into(db.invoices).insert(
          InvoicesCompanion(
            invoiceIdString: drift.Value(reference),
            clientId: drift.Value(clientId),
            issueDate: drift.Value(DateTime.now()),
            dueDate: drift.Value(DateTime.now()),
            totalAmount: const drift.Value(0),
            status: const drift.Value('Draft'),
          ),
        );
  }

  // Pushes the screen onto a route of its own so that saving, which pops, has
  // somewhere to pop back to.
  Future<void> openNewInvoiceScreen(WidgetTester tester) async {
    await tester.pumpWidget(
      Provider<AppDatabase>.value(
        value: db,
        child: MaterialApp(
          home: Builder(
            builder: (context) => Scaffold(
              body: ElevatedButton(
                onPressed: () => Navigator.of(context).push(
                  MaterialPageRoute(builder: (_) => const InvoiceEditScreen()),
                ),
                child: const Text('open'),
              ),
            ),
          ),
        ),
      ),
    );
    await tester.tap(find.text('open'));
    await tester.pumpAndSettle();
  }

  String shownReference(WidgetTester tester) {
    return tester.widget<EditableText>(find.byType(EditableText)).controller.text;
  }

  Future<void> selectClient(WidgetTester tester, String name) async {
    await tester.tap(find.byType(DropdownButtonFormField<Client>));
    await tester.pumpAndSettle();
    await tester.tap(find.text(name).last);
    await tester.pumpAndSettle();
  }

  testWidgets('an empty month starts at 001', (tester) async {
    await openNewInvoiceScreen(tester);

    expect(shownReference(tester), '${prefixForThisMonth()}001');
  });

  testWidgets('continues the sequence when the month already has invoices',
      (tester) async {
    final clientId = await insertClient('Acme');
    final prefix = prefixForThisMonth();
    await insertInvoice('${prefix}001', clientId);
    await insertInvoice('${prefix}002', clientId);
    // Another month and a hand-edited suffix must not influence this month.
    await insertInvoice('INV-1999-01-070', clientId);
    await insertInvoice('${prefix}003-B', clientId);

    await openNewInvoiceScreen(tester);

    expect(shownReference(tester), '${prefix}003');
  });

  testWidgets('gaps left by deleted invoices are not reused', (tester) async {
    final clientId = await insertClient('Acme');
    final prefix = prefixForThisMonth();
    await insertInvoice('${prefix}007', clientId);

    await openNewInvoiceScreen(tester);

    expect(shownReference(tester), '${prefix}008');
  });

  testWidgets('a code claimed while the screen is open is not duplicated',
      (tester) async {
    final clientId = await insertClient('Acme');
    final prefix = prefixForThisMonth();

    await openNewInvoiceScreen(tester);
    expect(shownReference(tester), '${prefix}001');

    await selectClient(tester, 'Acme');

    // Someone else takes the displayed code before this screen is saved.
    await insertInvoice('${prefix}001', clientId);

    await tester.tap(find.byTooltip('Save Invoice'));
    await tester.pumpAndSettle(const Duration(seconds: 1));

    final references = (await db.select(db.invoices).get())
        .map((invoice) => invoice.invoiceIdString)
        .toList();
    expect(references, containsAll(<String>['${prefix}001', '${prefix}002']));
    expect(references.toSet().length, references.length);
  });
}
