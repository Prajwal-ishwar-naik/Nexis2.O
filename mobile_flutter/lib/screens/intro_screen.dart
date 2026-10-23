import 'dart:math' as math;
import 'package:flutter/material.dart';
import '../theme.dart';
import '../widgets/fade_slide.dart';
import '../widgets/glass.dart';
import '../widgets/nexus_bot.dart';
import 'home_screen.dart';

/// Page route: soft fade + rise.
Route<T> softRoute<T>(Widget page, {bool replace = false}) => PageRouteBuilder<T>(
      opaque: false,
      transitionDuration: const Duration(milliseconds: 600),
      reverseTransitionDuration: const Duration(milliseconds: 500),
      pageBuilder: (_, __, ___) => page,
      transitionsBuilder: (_, anim, sec, child) {
        final curve = CurvedAnimation(parent: anim, curve: Curves.easeOutCubic);
        final secCurve = CurvedAnimation(parent: sec, curve: Curves.easeOutCubic);
        return FadeTransition(
          opacity: Tween<double>(begin: 1.0, end: 0.0).animate(secCurve),
          child: FadeTransition(
            opacity: curve,
            child: SlideTransition(
              position: Tween(begin: const Offset(0, .04), end: Offset.zero).animate(curve),
              child: child,
            ),
          ),
        );
      },
    );

class IntroScreen extends StatefulWidget {
  const IntroScreen({super.key});

  @override
  State<IntroScreen> createState() => _IntroScreenState();
}

class _IntroScreenState extends State<IntroScreen> with SingleTickerProviderStateMixin {
  late final AnimationController _ring =
      AnimationController(vsync: this, duration: const Duration(milliseconds: 2200))..repeat();
  Key _botKey = UniqueKey();
  bool _leaving = false;

  @override
  void dispose() {
    _ring.dispose();
    super.dispose();
  }

  Future<void> _go() async {
    if (_leaving) return;
    setState(() => _leaving = true);
    await Navigator.of(context).push(softRoute(const HomeScreen()));
    if (mounted) {
      setState(() => _leaving = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final sec = ModalRoute.of(context)?.secondaryAnimation;
    final content = Scaffold(
      body: SafeArea(
        child: Column(children: [
          Expanded(
            child: Center(
              child: FadeSlide(
                key: _botKey,
                duration: const Duration(milliseconds: 1000),
                from: const Offset(0, .12),
                scaleFrom: .85,
                child: LayoutBuilder(
                  builder: (_, box) => HeroNexusBot(height: math.min(box.maxHeight, 360)),
                ),
              ),
            ),
          ),
          AnimatedOpacity(
            duration: const Duration(milliseconds: 200),
            opacity: _leaving ? 0.0 : 1.0,
            child: FadeSlide(
              delay: const Duration(milliseconds: 350),
              child: Text('Meet Nexus,\nYour Smart AI\nAssistant.',
                  textAlign: TextAlign.center,
                  style: sans(34, w: FontWeight.w600, h: 1.18, ls: -0.4)),
            ),
          ),
          const SizedBox(height: 30),
          AnimatedOpacity(
            duration: const Duration(milliseconds: 200),
            opacity: _leaving ? 0.0 : 1.0,
            child: FadeSlide(
              delay: const Duration(milliseconds: 600),
              child: Row(mainAxisAlignment: MainAxisAlignment.spaceEvenly, children: [
                PressScale(
                  onTap: _leaving ? null : _go,
                  child: const Padding(
                      padding: EdgeInsets.all(14), child: Icon(Icons.close_rounded, size: 24, color: AC.soft)),
                ),
                PressScale(onTap: _leaving ? null : _go, scale: .92, child: _MicButton(ring: _ring)),
                PressScale(
                  onTap: _leaving ? null : () => setState(() => _botKey = UniqueKey()), // replay the entrance
                  child: const Padding(
                      padding: EdgeInsets.all(14), child: Icon(Icons.refresh_rounded, size: 24, color: AC.soft)),
                ),
              ]),
            ),
          ),
          const SizedBox(height: 26),
        ]),
      ),
    );

    if (sec == null) return content;
    return AnimatedBuilder(
      animation: sec,
      builder: (_, child) {
        final v = Curves.easeInOutCubic.transform(sec.value);
        return Opacity(
          opacity: (1.0 - v).clamp(0.0, 1.0),
          child: IgnorePointer(
            ignoring: sec.value > 0.05,
            child: child,
          ),
        );
      },
      child: content,
    );
  }
}

class _MicButton extends StatelessWidget {
  final Animation<double> ring;
  const _MicButton({required this.ring});

  @override
  Widget build(BuildContext context) => SizedBox(
        width: 96,
        height: 96,
        child: Stack(alignment: Alignment.center, children: [
          AnimatedBuilder(
            animation: ring,
            builder: (_, __) => Container(
              width: 68 + 28 * ring.value,
              height: 68 + 28 * ring.value,
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                border: Border.all(color: a(const Color(0xFF7FA6E8), .45 * (1 - ring.value)), width: 2),
              ),
            ),
          ),
          Container(
            width: 68,
            height: 68,
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              color: a(Colors.white, .95),
              boxShadow: const [BoxShadow(color: Color(0x1F1C2740), blurRadius: 26, offset: Offset(0, 10))],
            ),
            child: const Icon(Icons.mic_none_rounded, size: 28, color: AC.ink),
          ),
        ]),
      );
}
