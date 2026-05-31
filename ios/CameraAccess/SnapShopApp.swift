import SwiftUI

#if canImport(MWDATCore)
import MWDATCore
#endif

@main
struct SnapShopApp: App {
    // Start signed in if a token is already stored (persists across launches).
    @State private var isLoggedIn = Session.isLoggedIn

    init() {
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
