import SwiftUI

/// Phase 2 - Welcome + sign in. OAuth buttons are placeholders for the demo.
struct LoginView: View {
    @Binding var isLoggedIn: Bool
    @State private var hasStarted = false
    @State private var heroVisible = false
    @State private var heroSweep = false
    @State private var selectedMode: AuthMode = .login
    @State private var email = ""
    @State private var password = ""

    var body: some View {
        ZStack {
            AeroBackground(animatedBubbles: !hasStarted)

            if hasStarted {
                authContent
                    .transition(.move(edge: .trailing).combined(with: .opacity))
            } else {
                welcomeContent
                    .transition(.opacity)
            }
        }
        .animation(.spring(response: 0.48, dampingFraction: 0.86), value: hasStarted)
        .onAppear {
            heroVisible = true
            withAnimation(.easeInOut(duration: 2.2).delay(0.55).repeatForever(autoreverses: false)) {
                heroSweep = true
            }
        }
    }

    private var welcomeContent: some View {
        VStack(spacing: 32) {
            Spacer()

            AnimatedHeroCopy(isVisible: heroVisible, sweep: heroSweep)
                .padding(.horizontal, 26)

            Spacer()

            Button {
                hasStarted = true
            } label: {
                HStack {
                    Text("Get started")
                    Image(systemName: "arrow.right")
                }
            }
            .buttonStyle(AeroPrimaryButtonStyle())
            .padding(.horizontal, 28)
            .padding(.bottom, 30)
        }
    }

    private var authContent: some View {
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

                    Button {
                        // TODO: POST /auth/login, store Bearer token in Keychain.
                        isLoggedIn = true
                    } label: {
                        Text(selectedMode == .login ? "Continue" : "Create account")
                    }
                    .buttonStyle(AeroPrimaryButtonStyle())
                    .disabled(email.isEmpty || password.isEmpty)
                    .opacity(email.isEmpty || password.isEmpty ? 0.55 : 1)
                }
            }
            .padding(.horizontal, 22)

            VStack(spacing: 12) {
                Button {
                    // TODO: Wire Google OAuth.
                    isLoggedIn = true
                } label: {
                    OAuthButtonLabel(title: "Continue with Google", brand: .google)
                }
                .buttonStyle(AeroSecondaryButtonStyle())

                Button {
                    // TODO: Wire Sign in with Apple.
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

private struct AnimatedHeroCopy: View {
    let isVisible: Bool
    let sweep: Bool

    var body: some View {
        VStack(spacing: 18) {
            VStack(spacing: 4) {
                heroLine("Hi, welcome", size: 45, delay: 0.0)
                heroLine("to SnapShop", size: 47, delay: 0.16)
            }

            Text("Find what you see. Open the merchant cart in one tap.")
                .font(.system(size: 18, weight: .semibold, design: .rounded))
                .foregroundStyle(AeroTheme.deepGreen.opacity(0.72))
                .multilineTextAlignment(.center)
                .lineSpacing(3)
                .opacity(isVisible ? 1 : 0)
                .offset(y: isVisible ? 0 : 18)
                .animation(.spring(response: 0.70, dampingFraction: 0.86).delay(0.34), value: isVisible)
        }
    }

    private func heroLine(_ text: String, size: CGFloat, delay: Double) -> some View {
        Text(text)
            .font(.system(size: size, weight: .black, design: .rounded))
            .foregroundStyle(
                LinearGradient(
                    colors: [AeroTheme.deepGreen, AeroTheme.leaf],
                    startPoint: .leading,
                    endPoint: .trailing
                )
            )
            .multilineTextAlignment(.center)
            .lineLimit(1)
            .minimumScaleFactor(0.72)
            .overlay {
                GeometryReader { proxy in
                    Rectangle()
                        .fill(
                            LinearGradient(
                                colors: [
                                    Color.white.opacity(0.0),
                                    Color.white.opacity(0.72),
                                    Color.white.opacity(0.0)
                                ],
                                startPoint: .top,
                                endPoint: .bottom
                            )
                        )
                        .rotationEffect(.degrees(18))
                        .frame(width: proxy.size.width * 0.32, height: proxy.size.height * 2.2)
                        .offset(x: sweep ? proxy.size.width * 1.15 : -proxy.size.width * 0.45)
                }
                .mask(
                    Text(text)
                        .font(.system(size: size, weight: .black, design: .rounded))
                        .lineLimit(1)
                        .minimumScaleFactor(0.72)
                )
                .allowsHitTesting(false)
            }
            .opacity(isVisible ? 1 : 0)
            .blur(radius: isVisible ? 0 : 12)
            .scaleEffect(isVisible ? 1 : 0.94)
            .offset(y: isVisible ? 0 : 26)
            .animation(.spring(response: 0.78, dampingFraction: 0.78).delay(delay), value: isVisible)
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
                    .font(.system(size: 19, weight: .black, design: .rounded))
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
                    .fill(Color.white.opacity(0.72))
                    .overlay(
                        RoundedRectangle(cornerRadius: 16, style: .continuous)
                            .stroke(Color.white.opacity(0.82), lineWidth: 1)
                    )
            )
    }
}

#Preview {
    LoginView(isLoggedIn: .constant(false))
}
