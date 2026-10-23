import 'package:flutter/material.dart';
import '../theme.dart';
import '../widgets/chat_bubbles.dart';
import '../widgets/fade_slide.dart';
import '../widgets/glass.dart';
import '../widgets/nexus_composer.dart';
import 'chat_screen.dart';
import 'intro_screen.dart';
import '../widgets/nexus_bot.dart';
import '../widgets/pastel_background.dart';

class _Tool {
  final IconData icon;
  final String label, title, seed;
  const _Tool(this.icon, this.label, this.title, this.seed);
}

class _Recent {
  final IconData icon;
  final String title, sub;
  const _Recent(this.icon, this.title, this.sub);
}

const _tools = [
  _Tool(Icons.edit_outlined, 'AI text\nWriter', 'AI text writer', 'Help me write a short blog intro'),
  _Tool(Icons.image_outlined, 'AI image\ngenerator', 'Image generator', 'Create an image of a beautiful sky and beautiful sun'),
  _Tool(Icons.code_rounded, 'Code\nTutor', 'Code tutor', 'Teach me how to use Flutter widgets'),
  _Tool(Icons.notes_rounded, 'Smart\nSummarizer', 'Summarizer', 'Summarize a long report for me'),
];

const _recents = [
  _Recent(Icons.edit_outlined, 'Text writer', 'Healthy eating tips'),
  _Recent(Icons.image_outlined, 'Image generator', 'Dog in red plaid in house in winter'),
  _Recent(Icons.code_rounded, 'Code Tutor', 'How To Use visual Studio'),
  _Recent(Icons.notes_rounded, 'Summarizer', 'Quarterly report key points'),
  _Recent(Icons.edit_outlined, 'Text writer', 'Cover letter for a design job'),
  _Recent(Icons.code_rounded, 'Code Tutor', 'Explain async and await in Dart'),
];

class HomeScreen extends StatefulWidget {
  const HomeScreen({super.key});

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  String _query = '';
  bool _all = false;

  void _open(String title, String seed) =>
      Navigator.of(context).push(softRoute(ChatScreen(title: title, seed: seed)));

  void _goToRobot() {
    if (Navigator.of(context).canPop()) {
      Navigator.of(context).pop();
    } else {
      Navigator.of(context).pushReplacement(softRoute(const IntroScreen()));
    }
  }

  @override
  Widget build(BuildContext context) {
    final q = _query.trim().toLowerCase();
    var list = _recents
        .where((r) => q.isEmpty || r.title.toLowerCase().contains(q) || r.sub.toLowerCase().contains(q))
        .toList();
    if (!_all && q.isEmpty) list = list.take(3).toList();

    return Scaffold(
      body: Stack(
        fit: StackFit.expand,
        children: [
          const Positioned.fill(child: PastelBackground()),
          SafeArea(
            child: Column(children: [
              Expanded(
                child: ListView(
                  physics: const BouncingScrollPhysics(),
                  padding: const EdgeInsets.only(top: 6),
              children: [
                FadeSlide(
                  child: Padding(
                    padding: const EdgeInsets.symmetric(horizontal: 18),
                    child: Row(children: [
                      const UserAvatar(size: 46),
                      const Spacer(),
                      CircleBtn(icon: Icons.notifications_none_rounded, onTap: () => soon(context)),
                      const SizedBox(width: 8),
                      CircleBtn(icon: Icons.grid_view_rounded, onTap: () => soon(context)),
                    ]),
                  ),
                ),
                const SizedBox(height: 16),
                FadeSlide(
                  delay: const Duration(milliseconds: 100),
                  child: Padding(
                    padding: const EdgeInsets.symmetric(horizontal: 20),
                    child: Row(
                      mainAxisAlignment: MainAxisAlignment.spaceBetween,
                      crossAxisAlignment: CrossAxisAlignment.center,
                      children: [
                        Text('Ask\nAnything', style: sans(38, w: FontWeight.w600, h: 1.12, ls: -0.6)),
                        MouseRegion(
                          cursor: SystemMouseCursors.click,
                          child: PressScale(
                            onTap: _goToRobot,
                            child: const HeroNexusBot(height: 92),
                          ),
                        ),
                      ],
                    ),
                  ),
                ),
                const SizedBox(height: 18),
                FadeSlide(
                  delay: const Duration(milliseconds: 180),
                  child: Padding(
                    padding: const EdgeInsets.symmetric(horizontal: 18),
                    child: Glass(
                      radius: 28,
                      height: 52,
                      alpha: .55,
                      padding: const EdgeInsets.symmetric(horizontal: 16),
                      child: Row(children: [
                        const Icon(Icons.search_rounded, size: 20, color: AC.faint),
                        const SizedBox(width: 10),
                        Expanded(
                          child: TextField(
                            onChanged: (v) => setState(() => _query = v),
                            cursorColor: AC.ink,
                            style: sans(15),
                            decoration: InputDecoration(
                              isDense: true,
                              border: InputBorder.none,
                              hintText: 'Search…',
                              hintStyle: sans(15, color: AC.faint),
                            ),
                          ),
                        ),
                      ]),
                    ),
                  ),
                ),
                const SizedBox(height: 18),
                SizedBox(
                  height: 190,
                  child: ListView.separated(
                    physics: const BouncingScrollPhysics(),
                    scrollDirection: Axis.horizontal,
                    padding: const EdgeInsets.symmetric(horizontal: 18),
                    itemCount: _tools.length,
                    separatorBuilder: (_, __) => const SizedBox(width: 12),
                    itemBuilder: (_, i) => FadeSlide(
                      delay: Duration(milliseconds: 260 + i * 90),
                      from: const Offset(.25, 0),
                      child: _ToolCard(tool: _tools[i], onTap: () => _open(_tools[i].title, _tools[i].seed)),
                    ),
                  ),
                ),
                const SizedBox(height: 24),
                FadeSlide(
                  delay: const Duration(milliseconds: 450),
                  child: Padding(
                    padding: const EdgeInsets.symmetric(horizontal: 20),
                    child: Row(children: [
                      Text('Recent Activities', style: sans(17, w: FontWeight.w600)),
                      const Spacer(),
                      PressScale(
                        onTap: () => setState(() => _all = !_all),
                        child: Padding(
                          padding: const EdgeInsets.all(4),
                          child: Text(_all ? 'Show less' : 'See All', style: sans(13, color: AC.soft)),
                        ),
                      ),
                    ]),
                  ),
                ),
                const SizedBox(height: 10),
                AnimatedSize(
                  duration: const Duration(milliseconds: 350),
                  curve: Curves.easeOutCubic,
                  alignment: Alignment.topCenter,
                  child: Column(children: [
                    if (list.isEmpty)
                      Padding(
                          padding: const EdgeInsets.all(24),
                          child: Text('No matches', style: sans(14, color: AC.faint))),
                    for (var i = 0; i < list.length; i++)
                      FadeSlide(
                        key: ValueKey('${list[i].title}-${list[i].sub}'),
                        delay: Duration(milliseconds: 500 + i * 80),
                        child: Padding(
                          padding: const EdgeInsets.fromLTRB(18, 0, 18, 10),
                          child: _RecentTile(r: list[i], onTap: () => _open(list[i].title, list[i].sub)),
                        ),
                      ),
                  ]),
                ),
                const SizedBox(height: 8),
              ],
            ),
          ),
          NexusComposer(onSend: (t) => _open('New chat', t)),
        ]),
      ),
    ]),
  );
  }
}

class _ToolCard extends StatelessWidget {
  final _Tool tool;
  final VoidCallback onTap;
  const _ToolCard({required this.tool, required this.onTap});

  @override
  Widget build(BuildContext context) => PressScale(
        onTap: onTap,
        child: Glass(
          width: 168,
          radius: 30,
          alpha: .5,
          padding: const EdgeInsets.fromLTRB(18, 18, 16, 18),
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Container(
              width: 52,
              height: 52,
              decoration: BoxDecoration(shape: BoxShape.circle, color: a(Colors.white, .85)),
              child: Icon(tool.icon, size: 22, color: AC.ink),
            ),
            const Spacer(),
            Row(crossAxisAlignment: CrossAxisAlignment.end, children: [
              Expanded(child: Text(tool.label, style: sans(15.5, w: FontWeight.w600, h: 1.3))),
              const Icon(Icons.arrow_forward_rounded, size: 20),
            ]),
          ]),
        ),
      );
}

class _RecentTile extends StatelessWidget {
  final _Recent r;
  final VoidCallback onTap;
  const _RecentTile({required this.r, required this.onTap});

  @override
  Widget build(BuildContext context) => PressScale(
        onTap: onTap,
        scale: .98,
        child: Glass(
          radius: 24,
          alpha: .55,
          padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 13),
          child: Row(children: [
            Container(
              width: 42,
              height: 42,
              decoration: BoxDecoration(shape: BoxShape.circle, color: a(Colors.white, .85)),
              child: Icon(r.icon, size: 19, color: AC.ink),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Text(r.title, style: sans(15.5, w: FontWeight.w600)),
                const SizedBox(height: 2),
                Text(r.sub, maxLines: 1, overflow: TextOverflow.ellipsis, style: sans(12.5, color: AC.faint)),
              ]),
            ),
            const Icon(Icons.chevron_right_rounded, size: 22, color: AC.soft),
          ]),
        ),
      );
}
