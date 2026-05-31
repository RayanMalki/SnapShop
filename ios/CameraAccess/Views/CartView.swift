import SwiftUI

struct CartProduct: Codable {
    let variantId: String
    let title: String
    let priceMin: Int
    let currency: String
    let imageUrl: String
    let merchantDomain: String

    enum CodingKeys: String, CodingKey {
        case variantId = "variant_id"
        case title
        case priceMin = "price_min"
        case currency
        case imageUrl = "image_url"
        case merchantDomain = "merchant_domain"
    }
}

struct ScanResult: Codable {
    let status: String
    let visionSummary: String?
    let product: CartProduct?
    let continueUrl: String?
    let error: String?

    enum CodingKeys: String, CodingKey {
        case status
        case visionSummary = "vision_summary"
        case product
        case continueUrl = "continue_url"
        case error
    }
}

/// Phase 2 - single product cart; tap opens merchant continue_url in Safari.
struct CartView: View {
    @Environment(\.openURL) private var openURL
    @StateObject private var voiceManager = VoiceCommandManager()
    @StateObject private var glassesManager = MetaGlassesManager()
    @State private var result: ScanResult?
    @State private var isLoading = true
    @State private var scanPhase: ScanPhase = .idle
    @State private var workflowError: String?

    private let scanClient = ScanAPIClient()

    var body: some View {
        ZStack {
            AeroBackground()

            VStack(alignment: .leading, spacing: 28) {
                header

                voiceScanPanel

                Spacer(minLength: 28)

                if isLoading {
                    loadingCard
                } else if let product = result?.product, let urlString = result?.continueUrl,
                          let url = URL(string: urlString) {
                    productCard(product: product, url: url)
                } else {
                    emptyCard
                }

                Spacer()
            }
            .padding(.horizontal, 20)
            .padding(.top, 24)
        }
        .task { await loadCart() }
    }

    private var header: some View {
        HStack(alignment: .firstTextBaseline) {
            Text("Cart")
                .font(.system(size: 44, weight: .heavy, design: .rounded))
                .foregroundStyle(AeroTheme.deepGreen)

            Spacer()

            VStack(alignment: .trailing, spacing: 2) {
                Text("items")
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(AeroTheme.deepGreen.opacity(0.65))
                Text("\(result?.product == nil ? 0 : 1)")
                    .font(.title.bold())
                    .foregroundStyle(AeroTheme.deepGreen)
            }
        }
    }

    private var loadingCard: some View {
        GlassPanel {
            HStack(spacing: 16) {
                ProgressView()
                    .tint(AeroTheme.leaf)
                VStack(alignment: .leading, spacing: 5) {
                    Text("Looking for your find")
                        .font(.headline)
                    Text("Gemini and UCP are preparing the cart.")
                        .font(.caption)
                        .foregroundStyle(AeroTheme.deepGreen.opacity(0.68))
                }
                Spacer()
            }
            .foregroundStyle(AeroTheme.deepGreen)
        }
    }

    private var voiceScanPanel: some View {
        GlassPanel {
            VStack(alignment: .leading, spacing: 14) {
                HStack(spacing: 12) {
                    Image(systemName: scanPhase.symbolName)
                        .font(.title2.weight(.bold))
                        .foregroundStyle(AeroTheme.leaf)
                        .frame(width: 32)

                    VStack(alignment: .leading, spacing: 2) {
                        Text(scanPhase.title)
                            .font(.headline.weight(.bold))
                            .foregroundStyle(AeroTheme.deepGreen)

                        Text(statusLine)
                            .font(.caption.weight(.semibold))
                            .foregroundStyle(AeroTheme.deepGreen.opacity(0.62))
                    }

                    Spacer()

                    if scanPhase.isBusy {
                        ProgressView()
                            .tint(AeroTheme.leaf)
                    }
                }

                if !voiceManager.transcript.isEmpty {
                    Text("\" \(voiceManager.transcript) \"")
                        .font(.callout.weight(.medium))
                        .foregroundStyle(AeroTheme.deepGreen)
                        .lineLimit(3)
                        .padding(.horizontal, 12)
                        .padding(.vertical, 10)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .background(
                            RoundedRectangle(cornerRadius: 14, style: .continuous)
                                .fill(Color.white.opacity(0.50))
                        )
                }

                if let workflowError {
                    Text(workflowError)
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(.red.opacity(0.82))
                }

                HStack(spacing: 10) {
                    if glassesManager.needsRegistration {
                        Button {
                            Task { await glassesManager.registerWithMetaAI() }
                        } label: {
                            Label("Connect", systemImage: "eyeglasses")
                                .frame(maxWidth: .infinity)
                        }
                        .buttonStyle(AeroPrimaryButtonStyle())
                        .disabled(scanPhase.isBusy)
                    } else {
                        Button {
                            Task { await glassesManager.registerWithMetaAI() }
                        } label: {
                            Label("Registered", systemImage: "eyeglasses")
                        }
                        .buttonStyle(.bordered)
                        .tint(AeroTheme.leaf)
                        .disabled(scanPhase.isBusy)
                    }

                    Button {
                        Task { await runVoiceScan() }
                    } label: {
                        Label("Voice scan", systemImage: "waveform")
                            .frame(maxWidth: .infinity)
                    }
                    .buttonStyle(AeroPrimaryButtonStyle())
                    .disabled(scanPhase.isBusy || glassesManager.needsRegistration)
                }
            }
        }
    }

    private var statusLine: String {
        switch scanPhase {
        case .idle:
            return glassesManager.statusText
        case .listening:
            return "Speak naturally, e.g. find the green hoodie."
        case .capturing:
            return "Taking a photo from the Meta glasses."
        case .understanding:
            return "Sending speech and photo to Gemini."
        case .ready:
            return "Cart updated."
        case .failed:
            return glassesManager.statusText
        }
    }

    private var emptyCard: some View {
        GlassPanel {
            VStack(alignment: .leading, spacing: 12) {
                Image(systemName: "camera.viewfinder")
                    .font(.largeTitle)
                    .foregroundStyle(AeroTheme.leaf)

                Text("No product yet")
                    .font(.title3.bold())
                    .foregroundStyle(AeroTheme.deepGreen)

                Text("Capture from the glasses or run a scan from the backend, then your product will appear here.")
                    .font(.callout)
                    .foregroundStyle(AeroTheme.deepGreen.opacity(0.70))
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        }
    }

    private func productCard(product: CartProduct, url: URL) -> some View {
        Button {
            openURL(url)
        } label: {
            GlassPanel {
                HStack(spacing: 14) {
                    productImage(url: product.imageUrl)

                    VStack(alignment: .leading, spacing: 7) {
                        Text(product.title)
                            .font(.headline.weight(.bold))
                            .foregroundStyle(AeroTheme.deepGreen)
                            .lineLimit(2)

                        Text(product.merchantDomain)
                            .font(.caption.weight(.semibold))
                            .foregroundStyle(AeroTheme.deepGreen.opacity(0.58))

                        Text("Tap to open merchant cart")
                            .font(.caption2.weight(.medium))
                            .foregroundStyle(AeroTheme.leaf)
                            .padding(.top, 3)
                    }

                    Spacer(minLength: 8)

                    VStack(alignment: .trailing, spacing: 12) {
                        providerBadge(domain: product.merchantDomain)
                        Text(priceString(product))
                            .font(.title3.weight(.heavy))
                            .foregroundStyle(AeroTheme.deepGreen)
                            .lineLimit(1)
                    }
                }
            }
        }
        .buttonStyle(.plain)
    }

    private func productImage(url: String) -> some View {
        AsyncImage(url: URL(string: url)) { image in
            image.resizable().scaledToFill()
        } placeholder: {
            ZStack {
                LinearGradient(
                    colors: [Color.white.opacity(0.80), AeroTheme.mint.opacity(0.70)],
                    startPoint: .topLeading,
                    endPoint: .bottomTrailing
                )
                Image(systemName: "sparkles")
                    .foregroundStyle(AeroTheme.leaf)
            }
        }
        .frame(width: 74, height: 74)
        .clipShape(RoundedRectangle(cornerRadius: 18, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: 18, style: .continuous)
                .stroke(Color.white.opacity(0.80), lineWidth: 1)
        )
    }

    private func providerBadge(domain: String) -> some View {
        ZStack {
            RoundedRectangle(cornerRadius: 16, style: .continuous)
                .fill(Color.white.opacity(0.60))
                .frame(width: 58, height: 58)
                .overlay(
                    RoundedRectangle(cornerRadius: 16, style: .continuous)
                        .stroke(Color.white.opacity(0.84), lineWidth: 1)
                )

            Text(providerInitial(domain))
                .font(.title2.weight(.black))
                .foregroundStyle(AeroTheme.leaf)
        }
    }

    private func providerInitial(_ domain: String) -> String {
        guard let first = domain.first else { return "S" }
        return String(first).uppercased()
    }

    private func priceString(_ p: CartProduct) -> String {
        let dollars = Double(p.priceMin) / 100.0
        return String(format: "$%.2f %@", dollars, p.currency)
    }

    private func loadCart() async {
        isLoading = true
        defer { isLoading = false }
        guard let url = URL(string: "/cart/current", relativeTo: APIConfig.baseURL) else { return }
        let request = URLRequest(url: url)
        // request.setValue("Bearer …", forHTTPHeaderField: "Authorization")
        do {
            let (data, _) = try await URLSession.shared.data(for: request)
            result = try JSONDecoder().decode(ScanResult.self, from: data)
        } catch {
            result = nil
        }
    }

    private func runVoiceScan() async {
        workflowError = nil
        scanPhase = .listening

        do {
            try await voiceManager.requestPermissions()
            try voiceManager.startListening()
            try await Task.sleep(nanoseconds: 4_000_000_000)
            voiceManager.stopListening()

            let voiceContext = voiceManager.transcript.trimmingCharacters(in: .whitespacesAndNewlines)
            scanPhase = .capturing
            let imageData = try await glassesManager.capturePhoto()

            scanPhase = .understanding
            let scanResult = try await scanClient.uploadScan(
                imageData: imageData,
                voiceContext: voiceContext.isEmpty ? nil : voiceContext
            )
            result = scanResult
            scanPhase = scanResult.status == "ready" ? .ready : .failed
            if let error = scanResult.error {
                workflowError = error
            }
        } catch {
            voiceManager.stopListening()
            scanPhase = .failed
            workflowError = error.localizedDescription
        }
    }
}

private enum ScanPhase {
    case idle
    case listening
    case capturing
    case understanding
    case ready
    case failed

    var isBusy: Bool {
        switch self {
        case .listening, .capturing, .understanding:
            return true
        case .idle, .ready, .failed:
            return false
        }
    }

    var title: String {
        switch self {
        case .idle:
            return "Voice-guided scan"
        case .listening:
            return "Listening"
        case .capturing:
            return "Capturing"
        case .understanding:
            return "Understanding"
        case .ready:
            return "Cart ready"
        case .failed:
            return "Scan failed"
        }
    }

    var symbolName: String {
        switch self {
        case .idle:
            return "sparkles"
        case .listening:
            return "waveform"
        case .capturing:
            return "camera.viewfinder"
        case .understanding:
            return "brain.head.profile"
        case .ready:
            return "checkmark.circle.fill"
        case .failed:
            return "exclamationmark.triangle.fill"
        }
    }
}

#Preview {
    CartView()
}
