import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';

/// Design tokens: soft pastel / light.
class AC {
  static const ink = Color(0xFF14161D);
  static const soft = Color(0xFF5E6373);
  static const faint = Color(0xFFA2A7B4);
  static const base = Color(0xFFE9ECF0);
  static const sky = Color(0xFFCBDCF0);
  static const cream = Color(0xFFF5E4B6);
  static const cyan = Color(0xFF7FE9FF);
  static const dark = Color(0xFF12141C);
}

Color a(Color c, double o) => c.withAlpha((o.clamp(0, 1) * 255).round());

TextStyle sans(double size,
        {FontWeight w = FontWeight.w500, Color color = AC.ink, double? ls, double? h}) =>
    GoogleFonts.manrope(
        fontSize: size, fontWeight: w, color: color, letterSpacing: ls, height: h);

ThemeData buildTheme() => ThemeData(
      brightness: Brightness.light,
      useMaterial3: true,
      scaffoldBackgroundColor: Colors.transparent,
      colorScheme: ColorScheme.fromSeed(seedColor: const Color(0xFF7FA6E8)),
      textTheme: GoogleFonts.manropeTextTheme(ThemeData.light().textTheme),
      snackBarTheme: SnackBarThemeData(
        behavior: SnackBarBehavior.floating,
        backgroundColor: AC.dark,
        contentTextStyle: sans(13, color: Colors.white),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(14)),
      ),
    );

void soon(BuildContext context, [String msg = 'Coming soon']) {
  final m = ScaffoldMessenger.of(context);
  m.hideCurrentSnackBar();
  m.showSnackBar(SnackBar(content: Text(msg), duration: const Duration(milliseconds: 1400)));
}
