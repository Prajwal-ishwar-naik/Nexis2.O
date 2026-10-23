import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import '../theme.dart';
import 'glass.dart';

/// White pill input + dark round mic/send button (mic morphs into send).
class NexusComposer extends StatefulWidget {
  final bool busy;
  final String hint;
  final IconData leading;
  final ValueChanged<String> onSend;
  const NexusComposer({
    super.key,
    required this.onSend,
    this.busy = false,
    this.hint = 'Type your message',
    this.leading = Icons.add_rounded,
  });

  @override
  State<NexusComposer> createState() => NexusComposerState();
}

class NexusComposerState extends State<NexusComposer> {
  final _ctrl = TextEditingController();
  final _focus = FocusNode();
  bool _has = false;

  @override
  void initState() {
    super.initState();
    _ctrl.addListener(() {
      final h = _ctrl.text.trim().isNotEmpty;
      if (h != _has) setState(() => _has = h);
    });
    _focus.addListener(() => setState(() {}));
  }

  @override
  void dispose() {
    _ctrl.dispose();
    _focus.dispose();
    super.dispose();
  }

  void focus() => _focus.requestFocus();

  void _submit() {
    final t = _ctrl.text.trim();
    if (t.isEmpty || widget.busy) return;
    HapticFeedback.lightImpact();
    widget.onSend(t);
    _ctrl.clear();
  }

  @override
  Widget build(BuildContext context) {
    final focused = _focus.hasFocus;
    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 6, 16, 14),
      child: Row(crossAxisAlignment: CrossAxisAlignment.end, children: [
        Expanded(
          child: AnimatedContainer(
            duration: const Duration(milliseconds: 250),
            constraints: const BoxConstraints(minHeight: 54),
            padding: const EdgeInsets.only(left: 14, right: 8),
            decoration: BoxDecoration(
              color: a(Colors.white, .92),
              borderRadius: BorderRadius.circular(28),
              border: Border.all(color: focused ? const Color(0xFF9DB7E8) : a(Colors.white, .9), width: 1.4),
              boxShadow: [
                BoxShadow(
                    color: focused ? a(const Color(0xFF7FA6E8), .28) : const Color(0x141C2740),
                    blurRadius: focused ? 26 : 22,
                    offset: const Offset(0, 8)),
              ],
            ),
            child: Row(children: [
              Icon(widget.leading, size: 20, color: AC.faint),
              const SizedBox(width: 10),
              Expanded(
                child: TextField(
                  controller: _ctrl,
                  focusNode: _focus,
                  minLines: 1,
                  maxLines: 4,
                  keyboardType: TextInputType.multiline,
                  textInputAction: TextInputAction.newline,
                  cursorColor: AC.ink,
                  style: sans(15, color: AC.ink),
                  decoration: InputDecoration(
                    isDense: true,
                    border: InputBorder.none,
                    hintText: widget.hint,
                    hintStyle: sans(15, color: AC.faint),
                    contentPadding: const EdgeInsets.symmetric(vertical: 16),
                  ),
                ),
              ),
              AnimatedOpacity(
                opacity: _has ? 1 : .5,
                duration: const Duration(milliseconds: 200),
                child: const Icon(Icons.near_me_outlined, size: 20, color: AC.faint),
              ),
              const SizedBox(width: 8),
            ]),
          ),
        ),
        const SizedBox(width: 10),
        PressScale(
          scale: .9,
          onTap: () {
            if (_has) {
              _submit();
            } else if (!widget.busy) {
              soon(context, 'Voice input is not connected yet');
            }
          },
          child: AnimatedContainer(
            duration: const Duration(milliseconds: 250),
            width: 54,
            height: 54,
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              color: AC.dark,
              boxShadow: [
                BoxShadow(color: a(AC.dark, _has ? .35 : .2), blurRadius: _has ? 22 : 14, offset: const Offset(0, 8)),
              ],
            ),
            child: AnimatedSwitcher(
              duration: const Duration(milliseconds: 250),
              transitionBuilder: (c, anim) => ScaleTransition(
                  scale: anim,
                  child: RotationTransition(turns: Tween(begin: .8, end: 1.0).animate(anim), child: c)),
              child: widget.busy
                  ? const SizedBox(
                      key: ValueKey('busy'),
                      width: 20,
                      height: 20,
                      child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white70))
                  : Icon(_has ? Icons.arrow_upward_rounded : Icons.mic_none_rounded,
                      key: ValueKey(_has), color: Colors.white, size: 24),
            ),
          ),
        ),
      ]),
    );
  }
}
