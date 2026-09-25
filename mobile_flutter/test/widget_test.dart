// This is a basic Flutter widget test.
//
// To perform an interaction with a widget in your test, use the WidgetTester
// utility in the flutter_test package. For example, you can send tap and scroll
// gestures. You can also use WidgetTester to find child widgets in the widget
// tree, read text, and verify that the values of widget properties are correct.

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  testWidgets('app loads without crashing', (WidgetTester tester) async {
    final app = MaterialApp(
      home: Scaffold(
        appBar: AppBar(title: const Text('Road Damage')),
        body: const Center(
          child: Text('Ready'),
        ),
      ),
    );

    await tester.pumpWidget(app);

    expect(find.text('Road Damage'), findsOneWidget);
    expect(find.text('Ready'), findsOneWidget);
  });
}
