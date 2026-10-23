import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import '../chat_service.dart';
import '../theme.dart';
import '../widgets/chat_bubbles.dart';
import '../widgets/glass.dart';
import '../widgets/nexus_composer.dart';

class ChatScreen extends StatefulWidget {
  final String title;
  final String? seed; // auto-sent as the first message
  const ChatScreen({super.key, this.title = 'New chat', this.seed});

  @override
  State<ChatScreen> createState() => _ChatScreenState();
}

class _ChatScreenState extends State<ChatScreen> {
  final _messages = <Msg>[];
  final _scroll = ScrollController();
  final _composer = GlobalKey<NexusComposerState>();
  bool _busy = false;

  @override
  void initState() {
    super.initState();
    if (widget.seed != null) {
      Future.delayed(const Duration(milliseconds: 650), () {
        if (mounted) _send(widget.seed!);
      });
    }
  }

  @override
  void dispose() {
    _scroll.dispose();
    super.dispose();
  }

  void _toBottom() => WidgetsBinding.instance.addPostFrameCallback((_) {
        if (!_scroll.hasClients) return;
        _scroll.animateTo(_scroll.position.maxScrollExtent,
            duration: const Duration(milliseconds: 350), curve: Curves.easeOutCubic);
      });

  void _follow() {
    if (!_scroll.hasClients) return;
    final p = _scroll.position;
    if (p.maxScrollExtent - p.pixels < 140) _scroll.jumpTo(p.maxScrollExtent);
  }

  bool _wantsImage(String t) {
    final q = t.toLowerCase();
    return q.contains('image') || q.contains('picture') || q.contains('photo') || q.contains('draw');
  }

  Future<void> _send(String text) async {
    if (_busy) return;
    setState(() {
      _messages.add(Msg(true, text));
      _busy = true;
    });
    _toBottom();
    try {
      final reply = await ChatService.reply(text);
      if (!mounted) return;
      HapticFeedback.selectionClick();
      if (_wantsImage(text)) {
        setState(() => _messages.add(Msg(false, '', image: true)));
        _toBottom();
        await Future.delayed(const Duration(milliseconds: 1400));
        if (!mounted) return;
      }
      setState(() => _messages.add(Msg(false, reply)));
    } catch (e) {
      if (!mounted) return;
      setState(() => _messages.add(Msg(false, 'I couldn’t reach the API. Check API_URL and lib/chat_service.dart.\n\n$e', error: true)));
    } finally {
      if (mounted) setState(() => _busy = false);
      _toBottom();
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: SafeArea(
        child: Column(children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(18, 6, 18, 8),
            child: Row(children: [
              CircleBtn(icon: Icons.chevron_left_rounded, onTap: () => Navigator.of(context).pop()),
              Expanded(
                  child: Text(widget.title,
                      textAlign: TextAlign.center,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: sans(17, w: FontWeight.w600))),
              CircleBtn(icon: Icons.more_horiz_rounded, onTap: () => soon(context)),
            ]),
          ),
          Expanded(
            child: ListView.builder(
              controller: _scroll,
              physics: const BouncingScrollPhysics(),
              padding: const EdgeInsets.fromLTRB(18, 14, 18, 18),
              itemCount: _messages.length + (_busy ? 1 : 0),
              itemBuilder: (_, i) {
                if (i >= _messages.length) {
                  return const Padding(padding: EdgeInsets.only(top: 18), child: TypingRow());
                }
                final m = _messages[i];
                return Padding(
                  padding: EdgeInsets.only(top: i == 0 ? 0 : 18),
                  child: MessageRow(
                    key: ObjectKey(m),
                    msg: m,
                    typewriter: !m.isUser && !m.image && !m.error && i == _messages.length - 1,
                    onGrow: _follow,
                  ),
                );
              },
            ),
          ),
          NexusComposer(
              key: _composer, busy: _busy, leading: Icons.link_rounded, onSend: _send),
        ]),
      ),
    );
  }
}
