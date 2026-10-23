import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'screens/intro_screen.dart';
import 'theme.dart';
import 'widgets/pastel_background.dart';

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  SystemChrome.setSystemUIOverlayStyle(const SystemUiOverlayStyle(
    statusBarColor: Colors.transparent,
    statusBarIconBrightness: Brightness.dark,
    systemNavigationBarColor: Color(0xFFE9ECF0),
    systemNavigationBarIconBrightness: Brightness.dark,
  ));
  runApp(const NexusApp());
}

class NexusApp extends StatelessWidget {
  const NexusApp({super.key});

  @override
  Widget build(BuildContext context) => MaterialApp(
        title: 'Nexus AI',
        debugShowCheckedModeBanner: false,
        theme: buildTheme(),
        // Background lives above the Navigator so it stays smooth across page changes.
        builder: (context, child) => PhoneFrame(
          child: Stack(fit: StackFit.expand, children: [
            const Positioned.fill(child: PastelBackground()),
            child!,
          ]),
        ),
        home: const IntroScreen(),
      );
}

/// On wide web windows: shows the app in a 390x844 phone that scales to fit.
/// No effect on a real phone or narrow window.
class PhoneFrame extends StatelessWidget {
  final Widget child;
  const PhoneFrame({super.key, required this.child});

  static const _w = 390.0, _h = 844.0, _bezel = 12.0;

  @override
  Widget build(BuildContext context) {
    if (!kIsWeb) return child;
    return LayoutBuilder(builder: (context, box) {
      if (box.maxWidth < 520) return child;
      final mq = MediaQuery.of(context);
      return ColoredBox(
        color: const Color(0xFFDCE3EE),
        child: Padding(
          padding: const EdgeInsets.all(14),
          child: Center(
            child: FittedBox(
              fit: BoxFit.scaleDown,
              child: Container(
                width: _w + _bezel * 2,
                height: _h + _bezel * 2,
                padding: const EdgeInsets.all(_bezel),
                decoration: BoxDecoration(
                  color: const Color(0xFF0B0B0D),
                  borderRadius: BorderRadius.circular(60),
                  border: Border.all(color: const Color(0xFFC9CED8), width: 3),
                  boxShadow: const [
                    BoxShadow(color: Color(0x401C2740), blurRadius: 60, offset: Offset(0, 24)),
                  ],
                ),
                child: ClipRRect(
                  borderRadius: BorderRadius.circular(48),
                  child: Stack(fit: StackFit.expand, children: [
                    MediaQuery(
                      data: mq.copyWith(
                        size: const Size(_w, _h),
                        padding: const EdgeInsets.only(top: 52, bottom: 22),
                      ),
                      child: child,
                    ),
                    // fake status bar + dynamic island
                    Positioned(
                      top: 16,
                      left: 34,
                      child: Text('11:30', style: sans(15, w: FontWeight.w700)),
                    ),
                    const Positioned(
                      top: 17,
                      right: 30,
                      child: Row(children: [
                        Icon(Icons.signal_cellular_alt_rounded, size: 16, color: AC.ink),
                        SizedBox(width: 4),
                        Icon(Icons.wifi_rounded, size: 16, color: AC.ink),
                        SizedBox(width: 4),
                        Icon(Icons.battery_full_rounded, size: 18, color: AC.ink),
                      ]),
                    ),
                    Positioned(
                      top: 12,
                      left: 0,
                      right: 0,
                      child: Center(
                        child: Container(
                          width: 112,
                          height: 32,
                          decoration: BoxDecoration(color: Colors.black, borderRadius: BorderRadius.circular(20)),
                        ),
                      ),
                    ),
                    // home indicator
                    Positioned(
                      bottom: 8,
                      left: 0,
                      right: 0,
                      child: Center(
                        child: Container(
                          width: 120,
                          height: 4,
                          decoration: BoxDecoration(color: AC.ink, borderRadius: BorderRadius.circular(3)),
                        ),
                      ),
                    ),
                  ]),
                ),
              ),
            ),
          ),
        ),
      );
    });
  }
}
