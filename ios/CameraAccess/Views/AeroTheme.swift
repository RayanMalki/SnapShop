import SwiftUI

enum SnapShopTheme {
    static let purple = Color(red: 0.36, green: 0.25, blue: 0.88)
    static let ink = Color(red: 0.10, green: 0.09, blue: 0.14)
    static let secondaryInk = Color(red: 0.42, green: 0.40, blue: 0.48)
    static let surface = Color.white
    static let softPurple = Color(red: 0.96, green: 0.95, blue: 1.00)
    static let border = purple.opacity(0.16)

    static func displayFont(size: CGFloat) -> Font {
        .custom("HelveticaNeue-Bold", size: size)
    }

    static func actionFont(size: CGFloat) -> Font {
        .custom("HelveticaNeue-Medium", size: size)
    }

    static func bodyFont(size: CGFloat) -> Font {
        .custom("HelveticaNeue", size: size)
    }
}

/// Compatibility aliases used by the existing cart view.
enum AeroTheme {
    static let mint = SnapShopTheme.softPurple
    static let leaf = SnapShopTheme.purple
    static let deepGreen = SnapShopTheme.ink
    static let aqua = SnapShopTheme.softPurple
    static let lime = SnapShopTheme.purple
    static let glass = SnapShopTheme.surface
}

struct AeroBackground: View {
    var animatedBubbles = false

    var body: some View {
        Color.white
            .ignoresSafeArea()
    }
}

struct SnapShopLogo: View {
    var compact = false

    var body: some View {
        HStack(spacing: compact ? 9 : 12) {
            SnapShopMark(size: compact ? 38 : 52)

            VStack(alignment: .leading, spacing: compact ? -2 : 0) {
                Text("SnapShop")
                    .font(SnapShopTheme.displayFont(size: compact ? 25 : 40))
                    .foregroundStyle(SnapShopTheme.purple)

                if !compact {
                    Text("visual commerce")
                        .font(.caption.weight(.medium))
                        .foregroundStyle(SnapShopTheme.secondaryInk)
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
            RoundedRectangle(cornerRadius: size * 0.22, style: .continuous)
                .fill(SnapShopTheme.purple)

            Image(systemName: "camera.viewfinder")
                .font(.system(size: size * 0.42, weight: .semibold))
                .foregroundStyle(.white)
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
                RoundedRectangle(cornerRadius: 22, style: .continuous)
                    .fill(AeroTheme.glass)
                    .overlay(
                        RoundedRectangle(cornerRadius: 22, style: .continuous)
                            .stroke(SnapShopTheme.border, lineWidth: 1)
                    )
                    .shadow(color: SnapShopTheme.purple.opacity(0.06), radius: 16, x: 0, y: 8)
            )
    }
}

struct AeroPrimaryButtonStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(SnapShopTheme.actionFont(size: 17))
            .foregroundStyle(.white)
            .frame(maxWidth: .infinity)
            .padding(.vertical, 15)
            .background(
                Capsule()
                    .fill(SnapShopTheme.purple.opacity(configuration.isPressed ? 0.80 : 1))
            )
            .scaleEffect(configuration.isPressed ? 0.98 : 1)
    }
}

struct AeroSecondaryButtonStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(SnapShopTheme.actionFont(size: 17))
            .foregroundStyle(SnapShopTheme.ink)
            .frame(maxWidth: .infinity)
            .padding(.horizontal, 16)
            .padding(.vertical, 14)
            .background(
                Capsule()
                    .fill(
                        configuration.isPressed
                            ? SnapShopTheme.softPurple
                            : SnapShopTheme.surface
                    )
                    .overlay(
                        Capsule()
                            .stroke(SnapShopTheme.border, lineWidth: 1)
                    )
            )
            .scaleEffect(configuration.isPressed ? 0.98 : 1)
    }
}
