import 'dart:math' as math;
import 'package:flutter/material.dart';
import '../theme.dart';

/// Slowly drifting pastel blue + warm-cream light.
class PastelBackground extends StatefulWidget {
  const PastelBackground({super.key});

  @override
  State<PastelBackground> createState() => _PastelBackgroundState();
}

class _PastelBackgroundState extends State<PastelBackground>
    with SingleTickerProviderStateMixin {
  late final AnimationController _c =
      AnimationController(vsync: this, duration: const Duration(seconds: 20))..repeat();

  @override
  void dispose() {
    _c.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => RepaintBoundary(
        child: AnimatedBuilder(
          animation: _c,
          builder: (_, __) => CustomPaint(size: Size.infinite, painter: _P(_c.value)),
        ),
      );
}

class _P extends CustomPainter {
  final double t;
  _P(this.t);

  void _blob(Canvas c, Offset o, double r, Color col, double al) => c.drawCircle(
      o,
      r,
      Paint()
        ..shader = RadialGradient(colors: [a(col, al), a(col, 0)])
            .createShader(Rect.fromCircle(center: o, radius: r)));

  @override
  void paint(Canvas c, Size s) {
    c.drawRect(Offset.zero & s, Paint()..color = AC.base);
    final w = math.sin(t * math.pi * 2), v = math.cos(t * math.pi * 2);
    _blob(c, Offset(s.width * (.1 + .10 * w), s.height * (.08 + .04 * v)), s.width * .95,
        const Color(0xFFC5D8EF), .95);
    _blob(c, Offset(s.width * (.95 - .10 * w), s.height * (.22 + .05 * v)), s.width * .85,
        const Color(0xFFF7E3B0), .9);
    _blob(c, Offset(s.width * (.05 + .08 * v), s.height * (.80 - .04 * w)), s.width * .9,
        const Color(0xFFF4E1B2), .85);
    _blob(c, Offset(s.width * (.98 + .04 * w), s.height * (.98)), s.width * .9,
        const Color(0xFFC9D9EE), .9);
  }

  @override
  bool shouldRepaint(covariant _P o) => o.t != t;
}
