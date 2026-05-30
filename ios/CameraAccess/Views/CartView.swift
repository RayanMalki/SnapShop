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

    enum CodingKeys: String, CodingKey {
        case status
        case visionSummary = "vision_summary"
        case product
        case continueUrl = "continue_url"
    }
}

/// Phase 2 — single product cart; tap opens merchant continue_url in Safari.
struct CartView: View {
    @Environment(\.openURL) private var openURL
    @State private var result: ScanResult?
    @State private var isLoading = true

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            Text("Your find")
                .font(.title2.bold())

            if isLoading {
                ProgressView("Loading cart…")
            } else if let product = result?.product, let urlString = result?.continueUrl,
                      let url = URL(string: urlString) {
                Button {
                    openURL(url)
                } label: {
                    HStack(spacing: 16) {
                        AsyncImage(url: URL(string: product.imageUrl)) { image in
                            image.resizable().scaledToFill()
                        } placeholder: {
                            Color.gray.opacity(0.2)
                        }
                        .frame(width: 80, height: 80)
                        .clipShape(RoundedRectangle(cornerRadius: 8))

                        VStack(alignment: .leading, spacing: 4) {
                            Text(product.title).font(.headline)
                            Text(priceString(product))
                            Text(product.merchantDomain)
                                .font(.caption)
                                .foregroundStyle(.secondary)
                        }
                        Spacer()
                    }
                }
                .buttonStyle(.plain)

                Text("Tap to open store checkout")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            } else {
                Text("No product yet — capture or scan from backend.")
                    .foregroundStyle(.secondary)
            }
        }
        .padding()
        .task { await loadCart() }
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
        // request.setValue("Bearer …", forHTTPHeaderField: "Authorization")
        do {
            let (data, _) = try await URLSession.shared.data(for: request)
            result = try JSONDecoder().decode(ScanResult.self, from: data)
        } catch {
            result = nil
        }
    }
}

#Preview {
    CartView()
}
