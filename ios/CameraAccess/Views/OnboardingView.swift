import SwiftUI

struct OnboardingView: View {
    @Binding var didCompleteOnboarding: Bool
    @State private var contentVisible = false

    var body: some View {
        ZStack {
            Color.white
                .ignoresSafeArea()

            Image("WelcomeProducts")
                .resizable()
                .scaledToFill()
                .ignoresSafeArea()
                .allowsHitTesting(false)

            GeometryReader { proxy in
                ZStack {
                    VStack(spacing: 7) {
                        Text("SnapShop")
                            .font(SnapShopTheme.displayFont(size: 58))
                            .foregroundStyle(SnapShopTheme.purple)
                            .lineLimit(1)
                            .minimumScaleFactor(0.8)

                        Text("VERSION 0 · EARLY RELEASE")
                            .font(.system(size: 12, weight: .medium))
                            .foregroundStyle(.secondary)
                            .tracking(0.8)
                    }
                    .position(x: proxy.size.width / 2, y: proxy.size.height * 0.45)

                    VStack(spacing: 14) {
                        Text("What did you find?")
                            .font(SnapShopTheme.displayFont(size: 32))
                            .foregroundStyle(SnapShopTheme.purple)
                            .multilineTextAlignment(.center)

                        Text("Snap a product and find where\nto buy it instantly.")
                            .font(.system(size: 18, weight: .medium))
                            .foregroundStyle(.black)
                            .multilineTextAlignment(.center)
                            .lineSpacing(4)
                    }
                    .position(x: proxy.size.width / 2, y: proxy.size.height * 0.68)

                    VStack {
                        Spacer()

                        Button {
                            didCompleteOnboarding = true
                        } label: {
                            Text("Get started")
                        }
                        .buttonStyle(WelcomeButtonStyle())
                        .padding(.horizontal, 34)
                        .padding(.bottom, 34)
                    }
                }
            }
            .padding(.top, 32)
            .opacity(contentVisible ? 1 : 0)
            .offset(y: contentVisible ? 0 : 14)
        }
        .onAppear {
            withAnimation(.easeOut(duration: 0.55)) {
                contentVisible = true
            }
        }
    }
}

private struct WelcomeButtonStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(SnapShopTheme.actionFont(size: 20))
            .foregroundStyle(.white)
            .frame(maxWidth: .infinity)
            .padding(.vertical, 18)
            .background(
                Capsule()
                    .fill(SnapShopTheme.purple.opacity(configuration.isPressed ? 0.82 : 1))
            )
            .scaleEffect(configuration.isPressed ? 0.98 : 1)
    }
}

#Preview {
    OnboardingView(didCompleteOnboarding: .constant(false))
}
