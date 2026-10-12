import 'package:flutter/material.dart';

class ContentWidth extends StatelessWidget {
  final Widget child;
  final double maxWidth;
  const ContentWidth({super.key, required this.child, this.maxWidth = 1000});
  @override
  Widget build(BuildContext context) => Align(
    alignment: Alignment.topCenter,
    heightFactor: 1,
    child: ConstrainedBox(
      constraints: BoxConstraints(maxWidth: maxWidth),
      child: SizedBox(width: double.infinity, child: child),
    ),
  );
}

class WorkspaceBody extends StatelessWidget {
  final Widget child;
  final int selected;
  final ValueChanged<int> onSelect;
  const WorkspaceBody({
    super.key,
    required this.child,
    required this.selected,
    required this.onSelect,
  });
  @override
  Widget build(BuildContext context) {
    if (MediaQuery.sizeOf(context).width < 1000) return child;
    return Row(
      children: [
        NavigationRail(
          extended: true,
          backgroundColor: Theme.of(context).scaffoldBackgroundColor,
          selectedIndex: selected,
          onDestinationSelected: onSelect,
          destinations: const [
            NavigationRailDestination(
              icon: Icon(Icons.explore_outlined),
              selectedIcon: Icon(Icons.explore),
              label: Text('Discover'),
            ),
            NavigationRailDestination(
              icon: Icon(Icons.bookmark_border),
              selectedIcon: Icon(Icons.bookmark),
              label: Text('Saved'),
            ),
            NavigationRailDestination(
              icon: Icon(Icons.check_circle_outline),
              selectedIcon: Icon(Icons.check_circle),
              label: Text('Applied'),
            ),
            NavigationRailDestination(
              icon: Icon(Icons.history),
              label: Text('Dismissed'),
            ),
          ],
        ),
        const VerticalDivider(width: 1),
        Expanded(child: ContentWidth(child: child)),
      ],
    );
  }
}
