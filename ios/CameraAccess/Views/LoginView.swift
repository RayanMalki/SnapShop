import SwiftUI

/// Phase 2 — Sign in (Apple / email mock). Wire to POST /auth/login.
struct LoginView: View {
    @Binding var isLoggedIn: Bool
    @State private var email = ""

    var body: some View {
        VStack(spacing: 24) {
            Text("Snap & Shop")
                .font(.largeTitle.bold())

            TextField("Email (demo)", text: $email)
                .textContentType(.emailAddress)
                .autocapitalization(.none)
                .padding()
                .background(Color(.secondarySystemBackground))
                .cornerRadius(10)

            Button("Sign in") {
                // TODO: POST /auth/login, store Bearer token in Keychain
                isLoggedIn = true
            }
            .buttonStyle(.borderedProminent)
            .disabled(email.isEmpty)
        }
        .padding()
    }
}

#Preview {
    LoginView(isLoggedIn: .constant(false))
}
