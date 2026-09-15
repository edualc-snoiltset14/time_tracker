import 'package:flutter_test/flutter_test.dart';
import 'package:time_tracker/providers/app_navigation.dart';

void main() {
  group('AppNavigation', () {
    test('starts on the tasks tab', () {
      final navigation = AppNavigation();

      expect(navigation.currentTab, AppTab.tasks);
      expect(navigation.currentIndex, 0);
    });

    test('goToTab switches tab and notifies listeners', () {
      final navigation = AppNavigation();
      var notifications = 0;
      navigation.addListener(() => notifications++);

      navigation.goToTab(AppTab.timeTracker);

      expect(navigation.currentTab, AppTab.timeTracker);
      expect(navigation.currentIndex, 1);
      expect(notifications, 1);
    });

    test('goToTab does not notify when already on that tab', () {
      final navigation = AppNavigation();
      var notifications = 0;
      navigation.addListener(() => notifications++);

      navigation.goToTab(AppTab.tasks);

      expect(notifications, 0);
    });

    test('goToIndex maps a navigation bar index to its tab', () {
      final navigation = AppNavigation();

      navigation.goToIndex(AppTab.settings.index);

      expect(navigation.currentTab, AppTab.settings);
    });
  });
}
