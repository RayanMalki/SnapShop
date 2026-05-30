# iOS — Phase 2+

## Setup

1. Copy the Meta CameraAccess sample (Phase 3 glasses) or create a new SwiftUI app:

   ```bash
   cp -R ~/Documents/GitHub/meta-wearables-dat-ios/samples/CameraAccess ios/
   ```

2. Add `Views/LoginView.swift` and `Views/CartView.swift` (stubs provided under `ios/CameraAccess/Views/`).

3. Signing (Personal Team):
   - Team ID: `8RXQA62R8G`
   - Bundle ID: `com.rayanmalki.mpchackathon`
   - Remove **Hotspot** and **Access Wi-Fi Information** capabilities if signing fails.

4. Point the app at the Mac running FastAPI:

   ```bash
   ipconfig getifaddr en0
   ```

   Set `APIConfig.baseURL = "http://<IP>:8000"`.

## Flow

- **LoginView** → `POST /auth/login` (or mock)
- **CartView** → `GET /cart/current` or `POST /scan` after capture
- Tap product → `openURL(continue_url)` → merchant checkout
