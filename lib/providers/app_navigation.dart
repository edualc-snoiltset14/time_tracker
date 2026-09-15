// lib/providers/app_navigation.dart
import 'package:flutter/foundation.dart';

/// The tabs shown by MainScreen's BottomNavigationBar.
///
/// The order here is the order of the bar's items, so `AppTab.index` is the
/// index the BottomNavigationBar uses.
enum AppTab {
  tasks,
  timeTracker,
  projects,
  clients,
  expenses,
  invoices,
  reports,
  settings,
}

/// Holds the tab MainScreen is currently showing.
///
/// MainScreen owns the BottomNavigationBar but not the selected tab, so any
/// screen inside a tab can switch tabs by reading this from the context, e.g.
/// after starting a timer from the task list.
class AppNavigation extends ChangeNotifier {
  AppTab _currentTab = AppTab.tasks;

  AppTab get currentTab => _currentTab;

  /// The index the BottomNavigationBar should show.
  int get currentIndex => _currentTab.index;

  void goToTab(AppTab tab) {
    if (_currentTab == tab) return;
    _currentTab = tab;
    notifyListeners();
  }

  /// Convenience for the BottomNavigationBar's `onTap`, which reports an index.
  void goToIndex(int index) => goToTab(AppTab.values[index]);
}
