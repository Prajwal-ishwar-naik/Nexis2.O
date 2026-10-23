import 'dart:math' as math;
import 'dart:ui' as ui;
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import '../theme.dart';
import 'fade_slide.dart';
import 'glass.dart';

class Msg {
  final bool isUser;
  final String text;
  final bool image;
  final bool error;
  Msg(this.isUser, this.text, {this.image = false, this.error = false});
}

class UserAvatar extends StatelessWidget {
  final double size;
  const UserAvatar({super.key, this.size = 30});
  @override
  Widget build(BuildContext context) => Container(
        width: size,
        height: size,
        alignment: Alignment.center,
        decoration: const BoxDecoration(
            shape: BoxShape.circle,
            gradient: LinearGradient(
                begin: Alignment.topLeft,
                end: Alignment.bottomRight,
                colors: [Color(0xFF9DB7E8), Color(0xFF6D8FD6)])),
        child: Text('S', style: sans(size * .42, w: FontWeight.w700, color: Colors.white)),
      );
}

/// Small white sparkle avatar for Nexus; spins while [busy].
class BotAvatar extends StatefulWidget {
  final bool busy;
  const BotAvatar({super.key, this.busy = false});
  @override
  State<BotAvatar> createState() => _BotAvatarState();
}

class _BotAvatarState extends State<BotAvatar> with SingleTickerProviderStateMixin {
  late final AnimationController _c =
      AnimationController(vsync: this, duration: const Duration(seconds: 3));

  @override
  void initState() {
    super.initState();
    if (widget.busy) _c.repeat();
  }

  @override
  void dispose() {
    _c.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => Container(
        width: 32,
        height: 32,
        decoration: BoxDecoration(
          color: a(Colors.white, .9),
          shape: BoxShape.circle,
          boxShadow: const [BoxShadow(color: Color(0x141C2740), blurRadius: 10, offset: Offset(0, 3))],
        ),
        child: RotationTransition(
            turns: _c, child: const Icon(Icons.auto_awesome, size: 16, color: AC.ink)),
      );
}

class _Bubble extends StatelessWidget {
  final Widget child;
  final bool user;
  const _Bubble({required this.child, required this.user});
  @override
  Widget build(BuildContext context) => Container(
        constraints: const BoxConstraints(maxWidth: 270),
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
        decoration: BoxDecoration(
          color: a(Colors.white, user ? .88 : .80),
          borderRadius: BorderRadius.only(
            topLeft: Radius.circular(user ? 20 : 6),
            topRight: Radius.circular(user ? 6 : 20),
            bottomLeft: const Radius.circular(20),
            bottomRight: const Radius.circular(20),
          ),
          boxShadow: const [BoxShadow(color: Color(0x0F1C2740), blurRadius: 16, offset: Offset(0, 5))],
        ),
        child: child,
      );
}

class MessageRow extends StatelessWidget {
  final Msg msg;
  final bool typewriter;
  final VoidCallback onGrow;
  const MessageRow({super.key, required this.msg, required this.typewriter, required this.onGrow});

  @override
  Widget build(BuildContext context) {
    if (msg.isUser) {
      return FadeSlide(
        duration: const Duration(milliseconds: 420),
        from: const Offset(.15, .1),
        scaleFrom: .92,
        scaleAlignment: Alignment.bottomRight,
        child: Row(mainAxisAlignment: MainAxisAlignment.end, crossAxisAlignment: CrossAxisAlignment.start, children: [
          Flexible(
              child: _Bubble(
                  user: true, child: Text(msg.text, style: sans(15, h: 1.45)))),
          const SizedBox(width: 8),
          const UserAvatar(),
        ]),
      );
    }
    if (msg.image) {
      return FadeSlide(
        duration: const Duration(milliseconds: 450),
        from: const Offset(-.05, .08),
        child: const _ImageResult(),
      );
    }
    return FadeSlide(
      duration: const Duration(milliseconds: 450),
      from: const Offset(-.08, .08),
      child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
        const BotAvatar(),
        const SizedBox(width: 8),
        Flexible(child: _AssistantText(msg: msg, typewriter: typewriter, onGrow: onGrow)),
      ]),
    );
  }
}

class _AssistantText extends StatefulWidget {
  final Msg msg;
  final bool typewriter;
  final VoidCallback onGrow;
  const _AssistantText({required this.msg, required this.typewriter, required this.onGrow});
  @override
  State<_AssistantText> createState() => _AssistantTextState();
}

class _AssistantTextState extends State<_AssistantText> with SingleTickerProviderStateMixin {
  late final List<(String, bool)> _segs = _parse(widget.msg.text);
  late final int _total = _segs.fold(0, (s, e) => s + e.$1.length);
  late final AnimationController _c = AnimationController(
      vsync: this, duration: Duration(milliseconds: (_total * 12).clamp(400, 3600).toInt()));
  bool _copied = false;

  static List<(String, bool)> _parse(String s) {
    final out = <(String, bool)>[];
    var last = 0;
    for (final m in RegExp(r'\*\*(.+?)\*\*').allMatches(s)) {
      if (m.start > last) out.add((s.substring(last, m.start), false));
      out.add((m.group(1)!, true));
      last = m.end;
    }
    if (last < s.length) out.add((s.substring(last), false));
    return out;
  }

  @override
  void initState() {
    super.initState();
    if (widget.typewriter) {
      _c.addListener(widget.onGrow);
      _c.forward();
    } else {
      _c.value = 1;
    }
  }

  @override
  void dispose() {
    _c.dispose();
    super.dispose();
  }

  Future<void> _copy() async {
    HapticFeedback.lightImpact();
    await Clipboard.setData(ClipboardData(text: widget.msg.text.replaceAll('**', '')));
    if (!mounted) return;
    setState(() => _copied = true);
    await Future.delayed(const Duration(milliseconds: 1400));
    if (mounted) setState(() => _copied = false);
  }

  @override
  Widget build(BuildContext context) {
    final err = widget.msg.error;
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      _Bubble(
        user: false,
        child: AnimatedBuilder(
          animation: _c,
          builder: (_, __) {
            var left = (_c.value * _total).floor();
            final spans = <TextSpan>[];
            for (final (txt, bold) in _segs) {
              if (left <= 0) break;
              final take = txt.length <= left ? txt : txt.substring(0, left);
              left -= take.length;
              spans.add(TextSpan(text: take, style: bold ? sans(15, w: FontWeight.w700, h: 1.55) : null));
            }
            if (_c.isAnimating) {
              spans.add(TextSpan(text: ' ●', style: const TextStyle(fontSize: 9, color: Color(0xFF7FA6E8))));
            }
            return Text.rich(TextSpan(
                style: sans(15, color: err ? const Color(0xFFC0392B) : AC.ink, h: 1.55), children: spans));
          },
        ),
      ),
      AnimatedBuilder(
        animation: _c,
        builder: (_, __) => AnimatedOpacity(
          opacity: _c.isCompleted && !err ? 1 : 0,
          duration: const Duration(milliseconds: 350),
          child: IgnorePointer(
            ignoring: !_c.isCompleted || err,
            child: Padding(
              padding: const EdgeInsets.only(top: 6, left: 2),
              child: Row(mainAxisSize: MainAxisSize.min, children: [
                _icon(_copied ? Icons.check_rounded : Icons.copy_rounded, _copy,
                    color: _copied ? const Color(0xFF2E9E78) : null),
                _icon(Icons.thumb_up_alt_outlined, () => soon(context, 'Thanks for the feedback')),
                _icon(Icons.thumb_down_alt_outlined, () => soon(context, 'Thanks for the feedback')),
              ]),
            ),
          ),
        ),
      ),
    ]);
  }

  Widget _icon(IconData i, VoidCallback onTap, {Color? color}) => InkResponse(
        onTap: onTap,
        radius: 18,
        child: Padding(
          padding: const EdgeInsets.all(7),
          child: AnimatedSwitcher(
              duration: const Duration(milliseconds: 220),
              child: Icon(i, key: ValueKey(i), size: 15, color: color ?? AC.faint)),
        ),
      );
}

/// Generated-image placeholder: develops from a blur, like an image arriving.
class _ImageResult extends StatelessWidget {
  const _ImageResult();
  @override
  Widget build(BuildContext context) => Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        TweenAnimationBuilder<double>(
          tween: Tween(begin: 1, end: 0),
          duration: const Duration(milliseconds: 1500),
          curve: Curves.easeOutCubic,
          builder: (_, k, child) {
            final blurred = k > .02
                ? ImageFiltered(imageFilter: ui.ImageFilter.blur(sigmaX: 22 * k, sigmaY: 22 * k), child: child)
                : child!;
            return Opacity(opacity: 1 - .35 * k, child: blurred);
          },
          child: ClipRRect(
            borderRadius: BorderRadius.circular(26),
            child: const SizedBox(width: 270, height: 230, child: CustomPaint(painter: _SkyPainter())),
          ),
        ),
        const SizedBox(height: 4),
        Row(mainAxisSize: MainAxisSize.min, children: [
          for (final i in [Icons.copy_rounded, Icons.thumb_up_alt_outlined, Icons.thumb_down_alt_outlined, Icons.volume_up_outlined, Icons.refresh_rounded])
            InkResponse(
                radius: 18,
                onTap: () => soon(context),
                child: Padding(padding: const EdgeInsets.all(7), child: Icon(i, size: 15, color: AC.faint))),
        ]),
      ]);
}

class _SkyPainter extends CustomPainter {
  const _SkyPainter();
  @override
  void paint(Canvas c, Size s) {
    final r = Offset.zero & s;
    c.drawRect(r, Paint()
      ..shader = const LinearGradient(begin: Alignment.topCenter, end: Alignment.bottomCenter,
          colors: [Color(0xFF8FD3F4), Color(0xFFBFE4F5), Color(0xFFFBE3CF), Color(0xFFFFC9A6)], stops: [0, .45, .75, 1])
          .createShader(r));
    final glow = Offset(s.width * .78, s.height * .78);
    c.drawCircle(glow, s.width * .45, Paint()
      ..shader = RadialGradient(colors: [const Color(0xAAFFE7B0), const Color(0x00FFE7B0)])
          .createShader(Rect.fromCircle(center: glow, radius: s.width * .45)));
    final puff = Paint()
      ..color = const Color(0xF2FFFFFF)
      ..maskFilter = const MaskFilter.blur(BlurStyle.normal, 9);
    final pink = Paint()
      ..color = const Color(0x88FFD2C2)
      ..maskFilter = const MaskFilter.blur(BlurStyle.normal, 12);
    final rnd = math.Random(7);
    for (var i = 0; i < 16; i++) {
      final x = s.width * (.05 + .9 * i / 15);
      final y = s.height * (.62 + .22 * rnd.nextDouble());
      c.drawCircle(Offset(x, y + 8), 24 + rnd.nextDouble() * 20, pink);
      c.drawCircle(Offset(x, y), 22 + rnd.nextDouble() * 22, puff);
    }
    for (var i = 0; i < 6; i++) {
      c.drawCircle(Offset(s.width * (.1 + .8 * i / 5), s.height * (.9 + .06 * rnd.nextDouble())), 34, puff);
    }
  }

  @override
  bool shouldRepaint(covariant CustomPainter old) => false;
}

/// "Nexus is typing": spinning sparkle + shrinking wave dots.
class TypingRow extends StatefulWidget {
  const TypingRow({super.key});
  @override
  State<TypingRow> createState() => _TypingRowState();
}

class _TypingRowState extends State<TypingRow> with SingleTickerProviderStateMixin {
  late final AnimationController _c =
      AnimationController(vsync: this, duration: const Duration(milliseconds: 1200))..repeat();
  @override
  void dispose() {
    _c.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => FadeSlide(
        duration: const Duration(milliseconds: 300),
        child: Row(children: [
          const BotAvatar(busy: true),
          const SizedBox(width: 8),
          Glass(
            radius: 18,
            alpha: .8,
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 15),
            child: AnimatedBuilder(
              animation: _c,
              builder: (_, __) => Row(mainAxisSize: MainAxisSize.min, children: [
                for (var i = 0; i < 3; i++)
                  Builder(builder: (_) {
                    final k = (math.sin((_c.value - i * .14) * math.pi * 2) + 1) / 2;
                    return Container(
                      width: 6 + 3 * k,
                      height: 6 + 3 * k,
                      margin: const EdgeInsets.symmetric(horizontal: 2.5),
                      decoration: BoxDecoration(
                          shape: BoxShape.circle, color: Color.lerp(const Color(0xFFB9BEC9), AC.ink, k)),
                    );
                  }),
              ]),
            ),
          ),
        ]),
      );
}
