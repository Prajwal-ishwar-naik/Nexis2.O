import 'dart:math' as math;
import 'package:flutter/material.dart';
import '../theme.dart';

/// Hero wrapper for NexusBot enabling buttery-smooth flight between modes.
class HeroNexusBot extends StatelessWidget {
  final double height;
  const HeroNexusBot({super.key, required this.height});

  static const String heroTag = 'nexus_bot_hero';

  @override
  Widget build(BuildContext context) => Hero(
        tag: heroTag,
        createRectTween: (begin, end) => MaterialRectArcTween(begin: begin, end: end),
        flightShuttleBuilder: (_, anim, dir, __, toCtx) {
          final Hero toHero = toCtx.widget as Hero;
          return Material(
            color: Colors.transparent,
            child: FittedBox(
              fit: BoxFit.contain,
              child: toHero.child,
            ),
          );
        },
        child: SizedBox(
          width: height * 260 / 350,
          height: height,
          child: FittedBox(
            fit: BoxFit.contain,
            child: NexusBot(height: height),
          ),
        ),
      );
}

/// Original robot mascot, drawn in code. Floats, blinks, glows, waves its arms.
class NexusBot extends StatefulWidget {
  final double height;
  const NexusBot({super.key, this.height = 340});

  @override
  State<NexusBot> createState() => _NexusBotState();
}

class _NexusBotState extends State<NexusBot> with SingleTickerProviderStateMixin {
  late final AnimationController _c =
      AnimationController(vsync: this, duration: const Duration(seconds: 6))..repeat();

  @override
  void dispose() {
    _c.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => RepaintBoundary(
        child: AnimatedBuilder(
          animation: _c,
          builder: (_, __) => CustomPaint(
            size: Size(widget.height * 260 / 350, widget.height),
            painter: _BotPainter(_c.value),
          ),
        ),
      );
}

class _BotPainter extends CustomPainter {
  final double t;
  _BotPainter(this.t);
  static const tau = math.pi * 2;

  Paint _grad(Rect r, List<Color> cols, {Alignment center = const Alignment(-.3, -.5), double radius = 1}) =>
      Paint()..shader = RadialGradient(center: center, radius: radius, colors: cols).createShader(r);

  @override
  void paint(Canvas c, Size size) {
    c.scale(size.width / 260);
    final bob = 7 * math.sin(t * tau * 2);

    // ground shadow (shrinks as the bot rises)
    c.drawOval(
        Rect.fromCenter(center: const Offset(130, 343), width: 120 - bob * 2.2, height: 12),
        Paint()
          ..color = a(const Color(0xFF3A4660), .20)
          ..maskFilter = const MaskFilter.blur(BlurStyle.normal, 7));

    c.save();
    c.translate(0, -2 + bob);

    // antennas
    for (final side in [-1.0, 1.0]) {
      final base = Offset(130 + side * 30, 84);
      final tip = base + Offset(side * (20 + 4 * math.sin(t * tau * 3 + side)), -50 + 2 * math.sin(t * tau * 2));
      c.drawLine(base, tip, Paint()
        ..color = const Color(0xFF3A3D45)
        ..strokeWidth = 4
        ..strokeCap = StrokeCap.round);
      c.drawCircle(tip, 11, _grad(Rect.fromCircle(center: tip, radius: 11), const [Color(0xFF8A8F9B), Color(0xFF2A2C33), Color(0xFF14151A)]));
    }

    // ears
    for (final side in [-1.0, 1.0]) {
      final r = RRect.fromRectAndRadius(
          Rect.fromCenter(center: Offset(130 + side * 90, 150), width: 24, height: 52), const Radius.circular(12));
      c.drawRRect(r, Paint()..color = const Color(0xFFB4B9C4));
      c.drawRRect(r.deflate(5), Paint()..color = const Color(0xFF454952));
    }

    // arms (behind torso edge)
    for (final side in [-1.0, 1.0]) {
      c.save();
      c.translate(130 + side * 50, 248);
      c.rotate(-side * (0.32 + 0.10 * math.sin(t * tau * 2 + (side > 0 ? 0 : 1.6))));
      final arm = RRect.fromRectAndRadius(const Rect.fromLTWH(-11, -4, 22, 56), const Radius.circular(11));
      c.drawRRect(arm, _grad(arm.outerRect, const [Color(0xFFFFFFFF), Color(0xFFD8DCE4)]));
      c.drawRRect(
          RRect.fromRectAndRadius(const Rect.fromLTWH(-11, 34, 22, 18), const Radius.circular(9)),
          Paint()..color = const Color(0xFF8D929E));
      c.drawRect(const Rect.fromLTWH(-11, 28, 22, 4), Paint()..color = const Color(0xFF3A3D45));
      c.restore();
    }

    // legs + feet
    for (final side in [-1.0, 1.0]) {
      final x = 130 + side * 24;
      c.drawRRect(RRect.fromRectAndRadius(Rect.fromCenter(center: Offset(x, 306), width: 20, height: 22), const Radius.circular(6)),
          Paint()..color = const Color(0xFF3A3D45));
      final foot = RRect.fromRectAndRadius(Rect.fromCenter(center: Offset(x + side * 2, 324), width: 38, height: 24), const Radius.circular(12));
      c.drawRRect(foot, _grad(foot.outerRect, const [Color(0xFFF2F4F8), Color(0xFF9CA1AD)], center: const Alignment(-.2, -.6)));
      c.drawRRect(
          RRect.fromRectAndRadius(Rect.fromCenter(center: Offset(x + side * 2, 330), width: 38, height: 8), const Radius.circular(4)),
          Paint()..color = const Color(0xFF6C717D));
    }

    // torso
    final torso = RRect.fromRectAndRadius(const Rect.fromLTWH(84, 226, 92, 84), const Radius.circular(40));
    c.drawRRect(torso, _grad(torso.outerRect, const [Color(0xFFFFFFFF), Color(0xFFEDEFF4), Color(0xFFCDD2DB)], center: const Alignment(-.3, -.6)));
    c.drawCircle(const Offset(130, 268), 22, Paint()..color = a(Colors.white, .75));
    c.drawCircle(const Offset(130, 268), 22, Paint()
      ..style = PaintingStyle.stroke
      ..strokeWidth = 2
      ..color = a(const Color(0xFF8D929E), .35));
    c.drawLine(const Offset(112, 296), const Offset(148, 296),
        Paint()..color = a(const Color(0xFF3A3D45), .35)..strokeWidth = 2..strokeCap = StrokeCap.round);

    // neck
    c.drawRRect(RRect.fromRectAndRadius(const Rect.fromLTWH(112, 216, 36, 16), const Radius.circular(6)),
        Paint()..color = const Color(0xFF3A3D45));

    // head
    final head = RRect.fromRectAndRadius(const Rect.fromLTWH(45, 80, 170, 142), const Radius.circular(68));
    c.drawRRect(head.shift(const Offset(0, 6)), Paint()
      ..color = a(const Color(0xFF3A4660), .16)
      ..maskFilter = const MaskFilter.blur(BlurStyle.normal, 10));
    c.drawRRect(head, _grad(head.outerRect, const [Color(0xFFFFFFFF), Color(0xFFF0F2F6), Color(0xFFD2D7E0)], center: const Alignment(-.35, -.6), radius: 1.1));

    // visor
    final visor = RRect.fromRectAndRadius(const Rect.fromLTWH(60, 108, 140, 96), const Radius.circular(44));
    c.drawRRect(visor, Paint()
      ..shader = const LinearGradient(begin: Alignment.topCenter, end: Alignment.bottomCenter, colors: [Color(0xFF30333C), Color(0xFF0A0B0F)])
          .createShader(visor.outerRect));
    c.drawRRect(RRect.fromRectAndRadius(const Rect.fromLTWH(74, 114, 112, 12), const Radius.circular(6)),
        Paint()..color = a(Colors.white, .08));

    // eyes: glowing rings, blink every ~2s
    final ph = (t * 3) % 1;
    final blink = ph > .94 ? math.sin((ph - .94) / .06 * math.pi) : 0.0;
    final pulse = .5 + .5 * math.sin(t * tau * 4);
    for (final ex in [104.0, 156.0]) {
      c.save();
      c.translate(ex, 156);
      c.scale(1, 1 - .92 * blink);
      c.drawCircle(Offset.zero, 24, Paint()
        ..style = PaintingStyle.stroke
        ..strokeWidth = 11
        ..color = a(AC.cyan, .30 + .22 * pulse)
        ..maskFilter = const MaskFilter.blur(BlurStyle.normal, 7));
      c.drawCircle(Offset.zero, 18, Paint()..shader = RadialGradient(colors: [a(AC.cyan, .0), a(AC.cyan, .16 + .1 * pulse)]).createShader(Rect.fromCircle(center: Offset.zero, radius: 18)));
      c.drawCircle(Offset.zero, 21, Paint()
        ..style = PaintingStyle.stroke
        ..strokeWidth = 5.5
        ..color = const Color(0xFFD9FAFF));
      c.restore();
    }

    c.restore();
  }

  @override
  bool shouldRepaint(covariant _BotPainter o) => o.t != t;
}
