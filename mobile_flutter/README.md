# Nexus AI — Flutter

Light pastel AI assistant: animated robot intro, home with tools + recent activity, chat with typewriter replies.

## Run

```bash
flutter create . --platforms=web,android   # once
flutter pub get
flutter run -d chrome
```

On wide web windows the app shows inside a phone frame (see PhoneFrame in lib/main.dart).

## Connect your backend

`flutter run --dart-define=API_URL=https://your-api.example.com`
POST {API_URL}/chat {"message": "..."} -> {response|answer|message}. Edit lib/chat_service.dart for other schemas.

## Screens

- screens/intro_screen.dart — robot mascot (widgets/nexus_bot.dart), mic pulse, X / mic / replay
- screens/home_screen.dart — search (filters recents), swipeable tool cards, recent list (See All), composer
- screens/chat_screen.dart — bubbles, typing dots, generated-image placeholder, feedback icons
