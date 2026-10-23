import 'dart:convert';
import 'package:http/http.dart' as http;

/// Set with: flutter run --dart-define=API_URL=https://your-api.example.com
/// Leave empty to use local demo replies.
const String kApiUrl = String.fromEnvironment('API_URL');

class ChatService {
  /// POST {API_URL}/chat  {"message": "..."}  ->  {response|answer|message: "..."}
  /// Change the route / schema here to match your backend.
  static Future<String> reply(String message) async {
    if (kApiUrl.isEmpty) {
      await Future.delayed(const Duration(milliseconds: 1800));
      return _demo(message);
    }
    final base = kApiUrl.replaceAll(RegExp(r'/$'), '');
    final res = await http
        .post(Uri.parse('$base/chat'),
            headers: {'Content-Type': 'application/json'},
            body: jsonEncode({'message': message}))
        .timeout(const Duration(seconds: 45));
    if (res.statusCode != 200) throw Exception('API returned ${res.statusCode}');
    final data = jsonDecode(res.body) as Map<String, dynamic>;
    return (data['response'] ?? data['answer'] ?? data['message'] ??
            'The API responded, but no response text field was found.')
        .toString();
  }

  static String _demo(String m) {
    final q = m.toLowerCase();
    if (q.contains('image') || q.contains('picture') || q.contains('sky')) {
      return 'Here comes your image. I hope it captures the **wonder** you were looking for. Want it warmer, darker, or in another style?';
    }
    if (q.contains('code') || q.contains('flutter') || q.contains('dart') || q.contains('studio')) {
      return 'Let’s start with the basics. In Flutter, everything is a **widget**: layouts, text, buttons, even padding.\n\nTry building a small screen with a `Column`, then add a `Text` and a button. Want a step-by-step walkthrough?';
    }
    if (q.contains('summar') || q.contains('report')) {
      return 'Here’s a quick structure for a summary:\n\n• **Overview:** what it is about\n• **Key points:** the 3–5 things that matter\n• **Next steps:** what to do about it\n\nPaste the text and I’ll summarize it for you.';
    }
    if (q.contains('write') || q.contains('blog') || q.contains('eating') || q.contains('letter')) {
      return 'Happy to help you write that. A strong opening usually has a **hook**, a clear promise, and a friendly tone.\n\nTell me the audience and the mood, and I’ll draft a first version.';
    }
    return 'I’m **Nexus**, your AI assistant. You said: “$m”\n\nThis app is in demo mode. Set API_URL with --dart-define and edit lib/chat_service.dart to connect your real assistant.';
  }
}
