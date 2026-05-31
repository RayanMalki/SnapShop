import SwiftUI
import UserNotifications

#if canImport(MWDATCore)
import MWDATCore
#endif

@MainActor
final class NotificationManager: NSObject, UNUserNotificationCenterDelegate {
    static let shared = NotificationManager()

    private var didRequestAuthorization = false
    private var didInstallDelegate = false

    private override init() {}

    @discardableResult
    func requestAuthorizationIfNeeded() async -> Bool {
        installDelegateIfNeeded()

        if didRequestAuthorization {
            let settings = await UNUserNotificationCenter.current().notificationSettings()
            return settings.authorizationStatus == .authorized || settings.authorizationStatus == .provisional
        }
        didRequestAuthorization = true

        do {
            return try await UNUserNotificationCenter.current().requestAuthorization(
                options: [.alert, .badge, .sound]
            )
        } catch {
            NSLog("[SnapShop] Notification permission request failed: \(error)")
            return false
        }
    }

    nonisolated func userNotificationCenter(
        _ center: UNUserNotificationCenter,
        willPresent notification: UNNotification
    ) async -> UNNotificationPresentationOptions {
        [.banner, .list, .sound]
    }

    func sendItemFoundNotification(productTitle: String?) async {
        _ = await requestAuthorizationIfNeeded()

        let settings = await UNUserNotificationCenter.current().notificationSettings()
        guard settings.authorizationStatus == .authorized || settings.authorizationStatus == .provisional else {
            return
        }

        let content = UNMutableNotificationContent()
        content.title = "Item found"
        content.body = "Open SnapShop to see what we found."
        if let productTitle, !productTitle.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
            content.subtitle = productTitle
        }
        content.sound = .default

        let request = UNNotificationRequest(
            identifier: "scan-item-found-\(UUID().uuidString)",
            content: content,
            trigger: nil
        )

        do {
            try await UNUserNotificationCenter.current().add(request)
        } catch {
            NSLog("[SnapShop] Failed to schedule item-found notification: \(error)")
        }
    }

    private func installDelegateIfNeeded() {
        guard !didInstallDelegate else { return }
        didInstallDelegate = true
        UNUserNotificationCenter.current().delegate = self
    }
}

@main
struct SnapShopApp: App {
    // Start signed in if a token is already stored (persists across launches).
    @State private var isLoggedIn = Session.isLoggedIn

    init() {
        // Configure the Meta Wearables SDK BEFORE any view/StateObject (e.g.
        // CartView's MetaGlassesManager) accesses Wearables. Deferring this to
        // .task crashes when we launch straight into CartView (persisted login).
        #if canImport(MWDATCore)
        do {
            try Wearables.configure()
        } catch {
            NSLog("[SnapShop] Failed to configure Meta Wearables SDK: \(error)")
        }
        #endif
    }

    var body: some Scene {
        WindowGroup {
            Group {
                if isLoggedIn {
                    CartView(isLoggedIn: $isLoggedIn)
                } else {
                    LoginView(isLoggedIn: $isLoggedIn)
                }
            }
            .preferredColorScheme(.light)
            .onOpenURL { url in
                #if canImport(MWDATCore)
                Task {
                    _ = try? await Wearables.shared.handleUrl(url)
                }
                #endif
            }
        }
    }
}
