import SwiftUI

enum AeroTheme {
    static let mint = Color(red: 0.68, green: 0.96, blue: 0.78)
    static let leaf = Color(red: 0.16, green: 0.67, blue: 0.34)
    static let deepGreen = Color(red: 0.03, green: 0.28, blue: 0.17)
    static let aqua = Color(red: 0.42, green: 0.89, blue: 0.91)
    static let lime = Color(red: 0.80, green: 1.00, blue: 0.38)
    static let glass = Color.white.opacity(0.34)
}

struct AeroBackground: View {
    var animatedBubbles = false

    var body: some View {
        ZStack {
            LinearGradient(
                colors: [
                    Color(red: 0.88, green: 1.00, blue: 0.92),
                    Color(red: 0.50, green: 0.89, blue: 0.68),
                    Color(red: 0.15, green: 0.63, blue: 0.44)
                ],
                startPoint: .topLeading,
                endPoint: .bottomTrailing
            )
            .ignoresSafeArea()

            RadialGradient(
                colors: [Color.white.opacity(0.85), Color.white.opacity(0.0)],
                center: .topLeading,
                startRadius: 20,
                endRadius: 330
            )
            .ignoresSafeArea()

            if animatedBubbles {
                FloatingBubbles()
            }
        }
    }
}

struct SnapShopLogo: View {
    var compact = false

    var body: some View {
        HStack(spacing: compact ? 9 : 12) {
            SnapShopMark(size: compact ? 38 : 52)

            VStack(alignment: .leading, spacing: compact ? -2 : 0) {
                Text("SnapShop")
                    .font(.system(size: compact ? 25 : 34, weight: .black, design: .rounded))
                    .foregroundStyle(AeroTheme.deepGreen)

                if !compact {
                    Text("visual commerce")
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(AeroTheme.deepGreen.opacity(0.58))
                        .tracking(1.4)
                }
            }
        }
    }
}

struct SnapShopMark: View {
    let size: CGFloat

    var body: some View {
        ZStack {
            RoundedRectangle(cornerRadius: size * 0.30, style: .continuous)
                .fill(
                    LinearGradient(
                        colors: [Color.white.opacity(0.98), AeroTheme.lime.opacity(0.84)],
                        startPoint: .topLeading,
                        endPoint: .bottomTrailing
                    )
                )
                .overlay(
                    RoundedRectangle(cornerRadius: size * 0.30, style: .continuous)
                        .stroke(Color.white.opacity(0.88), lineWidth: 1.2)
                )
                .shadow(color: AeroTheme.deepGreen.opacity(0.18), radius: 14, x: 0, y: 8)

            Image(systemName: "camera.viewfinder")
                .font(.system(size: size * 0.42, weight: .bold))
                .foregroundStyle(AeroTheme.leaf)

            Circle()
                .fill(Color.white.opacity(0.82))
                .frame(width: size * 0.18, height: size * 0.18)
                .offset(x: -size * 0.22, y: -size * 0.22)
        }
        .frame(width: size, height: size)
    }
}

struct GlassPanel<Content: View>: View {
    @ViewBuilder var content: Content

    var body: some View {
        content
            .padding(18)
            .background(
                RoundedRectangle(cornerRadius: 28, style: .continuous)
                    .fill(AeroTheme.glass)
                    .overlay(
                        RoundedRectangle(cornerRadius: 28, style: .continuous)
                            .stroke(
                                LinearGradient(
                                    colors: [Color.white.opacity(0.88), AeroTheme.mint.opacity(0.42)],
                                    startPoint: .topLeading,
                                    endPoint: .bottomTrailing
                                ),
                                lineWidth: 1.5
                            )
                    )
                    .shadow(color: AeroTheme.deepGreen.opacity(0.20), radius: 24, x: 0, y: 12)
            )
    }
}

struct AeroPrimaryButtonStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.headline.weight(.semibold))
            .foregroundStyle(AeroTheme.deepGreen)
            .frame(maxWidth: .infinity)
            .padding(.vertical, 15)
            .background(
                RoundedRectangle(cornerRadius: 18, style: .continuous)
                    .fill(
                        LinearGradient(
                            colors: [Color.white.opacity(0.95), AeroTheme.lime.opacity(0.86)],
                            startPoint: .topLeading,
                            endPoint: .bottomTrailing
                        )
                    )
                    .overlay(
                        RoundedRectangle(cornerRadius: 18, style: .continuous)
                            .stroke(Color.white.opacity(0.72), lineWidth: 1)
                    )
                    .shadow(color: AeroTheme.deepGreen.opacity(configuration.isPressed ? 0.12 : 0.22), radius: configuration.isPressed ? 8 : 16, x: 0, y: configuration.isPressed ? 4 : 10)
            )
            .scaleEffect(configuration.isPressed ? 0.98 : 1)
    }
}

struct AeroSecondaryButtonStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .foregroundStyle(AeroTheme.deepGreen)
            .frame(maxWidth: .infinity)
            .padding(.horizontal, 16)
            .padding(.vertical, 14)
            .background(
                RoundedRectangle(cornerRadius: 22, style: .continuous)
                    .fill(
                        LinearGradient(
                            colors: [
                                Color.white.opacity(configuration.isPressed ? 0.66 : 0.86),
                                Color.white.opacity(configuration.isPressed ? 0.42 : 0.64)
                            ],
                            startPoint: .topLeading,
                            endPoint: .bottomTrailing
                        )
                    )
                    .overlay(
                        RoundedRectangle(cornerRadius: 22, style: .continuous)
                            .stroke(Color.white.opacity(0.92), lineWidth: 1.2)
                    )
                    .shadow(color: AeroTheme.deepGreen.opacity(configuration.isPressed ? 0.08 : 0.16), radius: configuration.isPressed ? 6 : 14, x: 0, y: configuration.isPressed ? 3 : 8)
            )
            .scaleEffect(configuration.isPressed ? 0.985 : 1)
    }
}

private struct BubbleData: Identifiable {
    let id = UUID()
    let x: CGFloat
    let y: CGFloat
    let size: CGFloat
    let duration: Double
    let delay: Double
}

private let bubbles: [BubbleData] = [
    BubbleData(x: 0.16, y: 1.05, size: 92, duration: 15, delay: 0.0),
    BubbleData(x: 0.78, y: 1.12, size: 132, duration: 20, delay: 1.4),
    BubbleData(x: 0.44, y: 0.98, size: 54, duration: 13, delay: 2.6),
    BubbleData(x: 0.88, y: 0.80, size: 76, duration: 17, delay: 0.9),
    BubbleData(x: 0.10, y: 0.60, size: 60, duration: 16, delay: 3.0)
]

private struct FloatingBubbles: View {
    @State private var rise = false

    var body: some View {
        GeometryReader { proxy in
            ForEach(bubbles) { bubble in
                Bubble(size: bubble.size)
                    .position(x: proxy.size.width * bubble.x, y: proxy.size.height * bubble.y)
                    .offset(y: rise ? -proxy.size.height * 1.25 : proxy.size.height * 0.18)
                    .animation(
                        .linear(duration: bubble.duration)
                        .delay(bubble.delay)
                        .repeatForever(autoreverses: false),
                        value: rise
                    )
            }
        }
        .ignoresSafeArea()
        .onAppear { rise = true }
    }
}

private struct Bubble: View {
    let size: CGFloat

    var body: some View {
        Circle()
            .fill(
                RadialGradient(
                    colors: [
                        Color.white.opacity(0.88),
                        AeroTheme.aqua.opacity(0.34),
                        AeroTheme.leaf.opacity(0.13)
                    ],
                    center: .topLeading,
                    startRadius: 2,
                    endRadius: size
                )
            )
            .overlay(
                Circle()
                    .stroke(Color.white.opacity(0.72), lineWidth: 1.2)
            )
            .overlay(alignment: .topLeading) {
                Circle()
                    .fill(Color.white.opacity(0.72))
                    .frame(width: size * 0.28, height: size * 0.18)
                    .offset(x: size * 0.18, y: size * 0.16)
                    .blur(radius: 1.2)
            }
            .frame(width: size, height: size)
            .opacity(0.72)
    }
}
