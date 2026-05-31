import SwiftUI

/// Phase 2 - sign in and account creation. OAuth buttons remain demo shortcuts.
struct LoginView: View {
    @Binding var isLoggedIn: Bool
    @State private var selectedMode: AuthMode = .login
    @State private var email = ""
    @State private var password = ""
    @State private var isSubmitting = false
    @State private var authError: String?

    private func submit() {
        isSubmitting = true
        authError = nil
        Task { @MainActor in
            defer { isSubmitting = false }
            do {
                let client = AuthAPIClient()
                let resp = selectedMode == .signup
                    ? try await client.signup(email: email, password: password)
                    : try await client.login(email: email, password: password)
                Session.token = resp.token
                isLoggedIn = true
            } catch ScanAPIError.serverError(let message) {
                authError = message
            } catch {
                authError = "Can't connect - is the backend running?"
            }
        }
    }

    var body: some View {
        ZStack {
            Color.white
                .ignoresSafeArea()

            Image("WelcomeProducts")
                .resizable()
                .scaledToFill()
                .ignoresSafeArea()
                .opacity(0.34)
                .allowsHitTesting(false)

            VStack(spacing: 24) {
                Spacer(minLength: 40)

                SnapShopLogo()
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding(.horizontal, 30)

                GlassPanel {
                    VStack(spacing: 18) {
                        Picker("Mode", selection: $selectedMode) {
                            Text("Login").tag(AuthMode.login)
                            Text("Sign up").tag(AuthMode.signup)
                        }
                        .pickerStyle(.segmented)
                        .tint(AeroTheme.leaf)

                        VStack(spacing: 12) {
                            TextField("Email", text: $email)
                                .textContentType(.emailAddress)
                                .autocapitalization(.none)
                                .disableAutocorrection(true)
                                .aeroField()

                            SecureField("Password", text: $password)
                                .textContentType(selectedMode == .login ? .password : .newPassword)
                                .aeroField()
                        }

                        if let authError {
                            Text(authError)
                                .font(.caption.weight(.semibold))
                                .foregroundStyle(.red.opacity(0.85))
                                .frame(maxWidth: .infinity, alignment: .leading)
                        }

                        Button {
                            submit()
                        } label: {
                            if isSubmitting {
                                ProgressView().tint(.white)
                            } else {
                                Text(selectedMode == .login ? "Continue" : "Create account")
                            }
                        }
                        .buttonStyle(AeroPrimaryButtonStyle())
                        .disabled(email.isEmpty || password.isEmpty || isSubmitting)
                        .opacity(email.isEmpty || password.isEmpty ? 0.55 : 1)
                    }
                }
                .padding(.horizontal, 22)
                .background(.white.opacity(0.72))

                VStack(spacing: 12) {
                    Button {
                        Session.token = "guest-google"
                        isLoggedIn = true
                    } label: {
                        OAuthButtonLabel(title: "Continue with Google", brand: .google)
                    }
                    .buttonStyle(AeroSecondaryButtonStyle())

                    Button {
                        Session.token = "guest-apple"
                        isLoggedIn = true
                    } label: {
                        OAuthButtonLabel(title: "Continue with Apple", brand: .apple)
                    }
                    .buttonStyle(AeroSecondaryButtonStyle())
                }
                .padding(.horizontal, 32)

                Spacer()
            }
        }
    }
}

private enum AuthMode {
    case login
    case signup
}

private struct OAuthButtonLabel: View {
    let title: String
    let brand: OAuthBrand

    var body: some View {
        HStack(spacing: 12) {
            brandIcon

            Text(title)
                .font(.headline.weight(.semibold))

            Spacer()

            Image(systemName: "arrow.right")
                .font(.subheadline.weight(.bold))
                .foregroundStyle(AeroTheme.deepGreen.opacity(0.56))
        }
        .padding(.horizontal, 2)
    }

    @ViewBuilder
    private var brandIcon: some View {
        switch brand {
        case .google:
            ZStack {
                Circle()
                    .fill(Color.white)
                Text("G")
                    .font(.system(size: 19, weight: .bold))
                    .foregroundStyle(
                        LinearGradient(
                            colors: [.blue, .red, .yellow, .green],
                            startPoint: .topLeading,
                            endPoint: .bottomTrailing
                        )
                    )
            }
            .frame(width: 34, height: 34)
        case .apple:
            ZStack {
                Circle()
                    .fill(AeroTheme.deepGreen)
                Image(systemName: "apple.logo")
                    .font(.system(size: 19, weight: .semibold))
                    .foregroundStyle(.white)
            }
            .frame(width: 34, height: 34)
        }
    }
}

private enum OAuthBrand {
    case google
    case apple
}

private extension View {
    func aeroField() -> some View {
        self
            .padding(.horizontal, 14)
            .padding(.vertical, 13)
            .background(
                RoundedRectangle(cornerRadius: 16, style: .continuous)
                    .fill(SnapShopTheme.softPurple)
                    .overlay(
                        RoundedRectangle(cornerRadius: 16, style: .continuous)
                            .stroke(SnapShopTheme.border, lineWidth: 1)
                    )
            )
    }
}

#Preview {
    LoginView(isLoggedIn: .constant(false))
}
