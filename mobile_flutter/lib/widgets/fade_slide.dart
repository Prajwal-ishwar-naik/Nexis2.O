import 'package:flutter/material.dart';

/// Fade + rise entrance with an optional delay (for staggering).
class FadeSlide extends StatefulWidget {
  final Widget child;
  final Duration delay;
  final Duration duration;
  final Offset from;
  final double scaleFrom;
  final Alignment scaleAlignment;
  const FadeSlide({
    super.key,
    required this.child,
    this.delay = Duration.zero,
    this.duration = const Duration(milliseconds: 650),
    this.from = const Offset(0, .2),
    this.scaleFrom = 1,
    this.scaleAlignment = Alignment.center,
  });

  @override
  State<FadeSlide> createState() => _FadeSlideState();
}

class _FadeSlideState extends State<FadeSlide> with SingleTickerProviderStateMixin {
  late final AnimationController _c = AnimationController(vsync: this, duration: widget.duration);
  late final CurvedAnimation _curve = CurvedAnimation(parent: _c, curve: Curves.easeOutCubic);

  @override
  void initState() {
    super.initState();
    if (widget.delay == Duration.zero) {
      _c.forward();
    } else {
      Future.delayed(widget.delay, () {
        if (mounted) _c.forward();
      });
    }
  }

  @override
  void dispose() {
    _c.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => FadeTransition(
        opacity: _curve,
        child: SlideTransition(
          position: Tween(begin: widget.from, end: Offset.zero).animate(_curve),
          child: widget.scaleFrom == 1
              ? widget.child
              : ScaleTransition(
                  alignment: widget.scaleAlignment,
                  scale: Tween(begin: widget.scaleFrom, end: 1.0).animate(_curve),
                  child: widget.child),
        ),
      );
}
