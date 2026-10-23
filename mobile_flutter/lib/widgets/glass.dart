import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import '../theme.dart';

/// Frosted white surface used for cards, pills and buttons.
class Glass extends StatelessWidget {
  final Widget child;
  final double radius;
  final EdgeInsetsGeometry padding;
  final double alpha;
  final double? width, height;
  final Alignment? alignment;
  final bool shadow;
  const Glass({
    super.key,
    required this.child,
    this.radius = 24,
    this.padding = EdgeInsets.zero,
    this.alpha = .62,
    this.width,
    this.height,
    this.alignment,
    this.shadow = true,
  });

  @override
  Widget build(BuildContext context) => Container(
        width: width,
        height: height,
        padding: padding,
        alignment: alignment,
        decoration: BoxDecoration(
          color: a(Colors.white, alpha),
          borderRadius: BorderRadius.circular(radius),
          border: Border.all(color: a(Colors.white, .8)),
          boxShadow: shadow
              ? const [BoxShadow(color: Color(0x141C2740), blurRadius: 24, offset: Offset(0, 8))]
              : null,
        ),
        child: child,
      );
}

/// Shrinks slightly while pressed.
class PressScale extends StatefulWidget {
  final Widget child;
  final VoidCallback? onTap;
  final double scale;
  const PressScale({super.key, required this.child, this.onTap, this.scale = .95});

  @override
  State<PressScale> createState() => _PressScaleState();
}

class _PressScaleState extends State<PressScale> {
  bool _down = false;
  @override
  Widget build(BuildContext context) => GestureDetector(
        behavior: HitTestBehavior.opaque,
        onTapDown: (_) => setState(() => _down = true),
        onTapCancel: () => setState(() => _down = false),
        onTapUp: (_) => setState(() => _down = false),
        onTap: widget.onTap == null
            ? null
            : () {
                HapticFeedback.selectionClick();
                widget.onTap!();
              },
        child: AnimatedScale(
          scale: _down ? widget.scale : 1,
          duration: const Duration(milliseconds: 130),
          curve: Curves.easeOut,
          child: widget.child,
        ),
      );
}

class CircleBtn extends StatelessWidget {
  final IconData icon;
  final VoidCallback? onTap;
  final double size;
  const CircleBtn({super.key, required this.icon, this.onTap, this.size = 44});

  @override
  Widget build(BuildContext context) => PressScale(
        onTap: onTap,
        child: Glass(
          width: size,
          height: size,
          radius: size / 2,
          alignment: Alignment.center,
          alpha: .75,
          child: Icon(icon, size: size * .45, color: AC.ink),
        ),
      );
}
