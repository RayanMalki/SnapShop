import SwiftUI

struct CartProduct: Codable {
    let variantId: String
    let title: String
    let priceMin: Int
    let currency: String
    let imageUrl: String
    let merchantDomain: String
    let merchantUrl: String?
    let checkoutUrl: String?

    /// Best link to open for this product (alternatives have no continue_url).
    var bestURL: URL? {
        let candidate = checkoutUrl ?? merchantUrl
            ?? (merchantDomain.isEmpty ? nil : "https://\(merchantDomain)")
        return candidate.flatMap(URL.init(string:))
    }

    enum CodingKeys: String, CodingKey {
        case variantId = "variant_id"
        case title
        case priceMin = "price_min"
        case currency
        case imageUrl = "image_url"
        case merchantDomain = "merchant_domain"
        case merchantUrl = "merchant_url"
        case checkoutUrl = "checkout_url"
    }
}

struct ScanResult: Codable {
    let status: String
    let visionSummary: String?
    let product: CartProduct?
    let continueUrl: String?
    let error: String?
    let matchQuality: String?      // "exact" | "similar"
    let matchReason: String?
    let confidence: Double?
    let lowConfidence: Bool?
    let alternatives: [CartProduct]?

    var isSimilarOnly: Bool { (matchQuality ?? "similar") != "exact" }

    enum CodingKeys: String, CodingKey {
        case status
        case visionSummary = "vision_summary"
        case product
        case continueUrl = "continue_url"
        case error
        case matchQuality = "match_quality"
        case matchReason = "match_reason"
        case confidence
        case lowConfidence = "low_confidence"
        case alternatives
    }
}

/// Phase 2 - single product cart; tap opens merchant continue_url in Safari.
struct CartView: View {
    @Binding var isLoggedIn: Bool
    @Environment(\.openURL) private var openURL
    @StateObject private var voiceManager = VoiceCommandManager()
    @StateObject private var glassesManager = MetaGlassesManager()
    @State private var result: ScanResult?
    @State private var isLoading = false
    @State private var scanPhase: ScanPhase = .idle
    @State private var workflowError: String?
    @State private var showHistory = false

    private let scanClient = ScanAPIClient()

    var body: some View {
        ZStack {
            AeroBackground()
                .ignoresSafeArea()

            ScrollView {
                VStack(alignment: .leading, spacing: 24) {
                    header

                    voiceScanPanel

                    if isLoading {
                        loadingCard
                    } else if let product = result?.product, let urlString = result?.continueUrl,
                              let url = URL(string: urlString) {
                        VStack(spacing: 14) {
                            if result?.isSimilarOnly == true {
                                similarBanner
                            }
                            productCard(product: product, url: url)
                            if let alts = result?.alternatives, !alts.isEmpty {
                                alternativesList(alts, similar: result?.isSimilarOnly == true)
                            }
                        }
                    } else {
                        emptyCard
                    }
                }
                .padding(.horizontal, 20)
                .padding(.top, 8)
                .padding(.bottom, 40)
                .frame(maxWidth: .infinity, alignment: .leading)
            }
        }
        .sheet(isPresented: $showHistory) { HistoryView() }
    }

    private var header: some View {
        HStack(alignment: .firstTextBaseline) {
            Text("Cart")
                .font(SnapShopTheme.displayFont(size: 48))
                .foregroundStyle(SnapShopTheme.purple)

            Spacer()

            Button {
                showHistory = true
            } label: {
                Image(systemName: "clock.arrow.circlepath")
                    .font(.title2.weight(.bold))
                    .foregroundStyle(AeroTheme.leaf)
                    .padding(10)
                    .background(Circle().fill(SnapShopTheme.softPurple))
            }

            Button {
                Session.clear()
                isLoggedIn = false
            } label: {
                Image(systemName: "rectangle.portrait.and.arrow.right")
                    .font(.title2.weight(.bold))
                    .foregroundStyle(SnapShopTheme.purple)
                    .padding(10)
                    .background(Circle().fill(SnapShopTheme.softPurple))
            }
            .padding(.trailing, 8)

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
                                .fill(SnapShopTheme.softPurple)
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
            return "Parle naturellement, ex. « la tuque noire » ou « the green hoodie »."
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

    private var similarBanner: some View {
        GlassPanel {
            HStack(spacing: 12) {
                Image(systemName: "exclamationmark.magnifyingglass")
                    .font(.title2.weight(.bold))
                    .foregroundStyle(.orange)
                    .frame(width: 30)

                VStack(alignment: .leading, spacing: 3) {
                    Text("Not sure this is your exact product")
                        .font(.subheadline.weight(.bold))
                        .foregroundStyle(AeroTheme.deepGreen)
                    Text("Here is the closest match we found.")
                        .font(.caption.weight(.medium))
                        .foregroundStyle(AeroTheme.deepGreen.opacity(0.7))
                }
                Spacer(minLength: 4)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        }
    }

    private func alternativesList(_ items: [CartProduct], similar: Bool) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(similar ? "Other similar results" : "Other options")
                .font(.caption.weight(.bold))
                .foregroundStyle(AeroTheme.deepGreen.opacity(0.65))
                .padding(.leading, 4)

            ForEach(items.indices, id: \.self) { i in
                alternativeRow(items[i])
            }
        }
    }

    private func alternativeRow(_ product: CartProduct) -> some View {
        Button {
            if let url = product.bestURL { openURL(url) }
        } label: {
            HStack(spacing: 12) {
                AsyncImage(url: URL(string: product.imageUrl)) { image in
                    image.resizable().scaledToFill()
                } placeholder: {
                    SnapShopTheme.softPurple
                }
                .frame(width: 48, height: 48)
                .clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))

                VStack(alignment: .leading, spacing: 2) {
                    Text(product.title)
                        .font(.subheadline.weight(.semibold))
                        .foregroundStyle(AeroTheme.deepGreen)
                        .lineLimit(2)
                    Text(product.merchantDomain)
                        .font(.caption2.weight(.medium))
                        .foregroundStyle(AeroTheme.deepGreen.opacity(0.55))
                }

                Spacer(minLength: 6)

                Text(priceString(product))
                    .font(.subheadline.weight(.bold))
                    .foregroundStyle(AeroTheme.deepGreen)
                    .lineLimit(1)
            }
            .padding(10)
            .background(
                RoundedRectangle(cornerRadius: 14, style: .continuous)
                    .fill(SnapShopTheme.softPurple)
            )
        }
        .buttonStyle(.plain)
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
                SnapShopTheme.softPurple
                Image(systemName: "photo")
                    .foregroundStyle(.secondary)
            }
        }
        .frame(width: 74, height: 74)
        .clipShape(RoundedRectangle(cornerRadius: 18, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: 18, style: .continuous)
                .stroke(SnapShopTheme.border, lineWidth: 1)
        )
    }

    private func providerBadge(domain: String) -> some View {
        ZStack {
            RoundedRectangle(cornerRadius: 16, style: .continuous)
                .fill(SnapShopTheme.softPurple)
                .frame(width: 58, height: 58)
                .overlay(
                    RoundedRectangle(cornerRadius: 16, style: .continuous)
                        .stroke(SnapShopTheme.border, lineWidth: 1)
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
        var request = URLRequest(url: url)
        Session.authorize(&request)
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
            let voiceContext = try await voiceManager.listenFor(maxSeconds: 7)
            scanPhase = .capturing
            let imageData = try await glassesManager.capturePhoto()

            scanPhase = .understanding
            let scanResult = try await scanClient.uploadScan(
                imageData: imageData,
                voiceContext: voiceContext.isEmpty ? nil : voiceContext
            )
            result = scanResult
            scanPhase = scanResult.status == "ready" ? .ready : .failed
            if scanResult.status == "ready", scanResult.product != nil {
                await NotificationManager.shared.sendItemFoundNotification(
                    productTitle: scanResult.product?.title
                )
            }
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
    CartView(isLoggedIn: .constant(true))
}

// MARK: - History ("My finds")

/// Lists the signed-in user's past scans (GET /history), newest first.
struct HistoryView: View {
    @Environment(\.dismiss) private var dismiss
    @Environment(\.openURL) private var openURL
    @State private var items: [ScanResult] = []
    @State private var isLoading = true

    var body: some View {
        ZStack {
            AeroBackground()

            VStack(alignment: .leading, spacing: 18) {
                HStack {
                    Text("My finds")
                        .font(SnapShopTheme.displayFont(size: 36))
                        .foregroundStyle(SnapShopTheme.purple)
                    Spacer()
                    Button { dismiss() } label: {
                        Image(systemName: "xmark.circle.fill")
                            .font(.title2)
                            .foregroundStyle(AeroTheme.deepGreen.opacity(0.5))
                    }
                }

                if isLoading {
                    ProgressView().tint(AeroTheme.leaf)
                        .frame(maxWidth: .infinity, minHeight: 120)
                } else if items.isEmpty {
                    Text("No finds yet. Scan a product to get started.")
                        .font(.callout)
                        .foregroundStyle(AeroTheme.deepGreen.opacity(0.7))
                        .padding(.top, 24)
                } else {
                    ScrollView {
                        VStack(spacing: 10) {
                            ForEach(items.indices, id: \.self) { i in
                                if let product = items[i].product {
                                    historyRow(items[i], product: product)
                                }
                            }
                        }
                        .padding(.bottom, 24)
                    }
                }

                Spacer()
            }
            .padding(20)
        }
        .task { await load() }
    }

    private func historyRow(_ scan: ScanResult, product: CartProduct) -> some View {
        Button {
            let link = scan.continueUrl.flatMap { URL(string: $0) } ?? product.bestURL
            if let link { openURL(link) }
        } label: {
            HStack(spacing: 12) {
                AsyncImage(url: URL(string: product.imageUrl)) { img in
                    img.resizable().scaledToFill()
                } placeholder: {
                    SnapShopTheme.softPurple
                }
                .frame(width: 54, height: 54)
                .clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))

                VStack(alignment: .leading, spacing: 2) {
                    Text(product.title)
                        .font(.subheadline.weight(.semibold))
                        .foregroundStyle(AeroTheme.deepGreen)
                        .lineLimit(2)
                    Text(product.merchantDomain)
                        .font(.caption2)
                        .foregroundStyle(AeroTheme.deepGreen.opacity(0.55))
                }

                Spacer(minLength: 6)

                Text(String(format: "$%.2f %@", Double(product.priceMin) / 100.0, product.currency))
                    .font(.subheadline.weight(.bold))
                    .foregroundStyle(AeroTheme.deepGreen)
                    .lineLimit(1)
            }
            .padding(12)
            .background(
                RoundedRectangle(cornerRadius: 16, style: .continuous)
                    .fill(SnapShopTheme.softPurple)
            )
        }
        .buttonStyle(.plain)
    }

    private func load() async {
        isLoading = true
        defer { isLoading = false }
        guard let url = URL(string: "/history", relativeTo: APIConfig.baseURL) else { return }
        var request = URLRequest(url: url)
        Session.authorize(&request)
        do {
            let (data, _) = try await URLSession.shared.data(for: request)
            items = try JSONDecoder().decode([ScanResult].self, from: data)
        } catch {
            items = []
        }
    }
}
