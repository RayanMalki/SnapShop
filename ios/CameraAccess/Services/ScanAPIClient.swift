import Foundation

struct ScanAPIClient {
    func uploadScan(imageData: Data, voiceContext: String?) async throws -> ScanResult {
        guard let url = URL(string: "/scan", relativeTo: APIConfig.baseURL) else {
            throw ScanAPIError.invalidURL
        }

        let boundary = "Boundary-\(UUID().uuidString)"
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("multipart/form-data; boundary=\(boundary)", forHTTPHeaderField: "Content-Type")
        Session.authorize(&request)
        request.httpBody = multipartBody(
            boundary: boundary,
            imageData: imageData,
            voiceContext: voiceContext
        )

        let (data, response) = try await URLSession.shared.data(for: request)
        guard let httpResponse = response as? HTTPURLResponse,
              200..<300 ~= httpResponse.statusCode else {
            if let scanError = try? JSONDecoder().decode(ScanResult.self, from: data),
               let message = scanError.error {
                throw ScanAPIError.serverError(message)
            }
            throw ScanAPIError.badResponse
        }
        return try JSONDecoder().decode(ScanResult.self, from: data)
    }

    private func multipartBody(boundary: String, imageData: Data, voiceContext: String?) -> Data {
        var body = Data()

        if let voiceContext, !voiceContext.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
            body.appendMultipartField(
                name: "voice_context",
                value: voiceContext,
                boundary: boundary
            )
        }

        body.append("--\(boundary)\r\n")
        body.append("Content-Disposition: form-data; name=\"file\"; filename=\"glasses-capture.jpg\"\r\n")
        body.append("Content-Type: image/jpeg\r\n\r\n")
        body.append(imageData)
        body.append("\r\n")
        body.append("--\(boundary)--\r\n")

        return body
    }
}

enum ScanAPIError: LocalizedError {
    case invalidURL
    case badResponse
    case serverError(String)

    var errorDescription: String? {
        switch self {
        case .invalidURL:
            return "Invalid scan URL."
        case .badResponse:
            return "The scan request failed."
        case .serverError(let message):
            return message
        }
    }
}

// MARK: - Auth / session

/// Stores the Snap & Shop bearer token (the backend uses it as the user_id, so
/// each signed-in user gets their own cart + scan history). Persisted in
/// UserDefaults — fine for the demo; move to Keychain for production.
enum Session {
    private static let key = "snapshop.token"

    static var token: String? {
        get { UserDefaults.standard.string(forKey: key) }
        set { UserDefaults.standard.set(newValue, forKey: key) }
    }

    static var isLoggedIn: Bool {
        guard let token, !token.isEmpty else { return false }
        if token == "anonymous-demo" {
            clear()
            return false
        }
        return true
    }

    static func clear() { UserDefaults.standard.removeObject(forKey: key) }

    /// Adds `Authorization: Bearer <token>` to a request when signed in.
    static func authorize(_ request: inout URLRequest) {
        if let t = token, !t.isEmpty {
            request.setValue("Bearer \(t)", forHTTPHeaderField: "Authorization")
        }
    }
}

struct AuthResponse: Codable {
    let token: String
    let userId: String

    enum CodingKeys: String, CodingKey {
        case token
        case userId = "user_id"
    }
}

struct AuthAPIClient {
    /// POST /auth/login — verifies credentials, returns a JWT.
    func login(email: String, password: String) async throws -> AuthResponse {
        try await authRequest(path: "/auth/login", email: email, password: password)
    }

    /// POST /auth/signup — creates the account, returns a JWT.
    func signup(email: String, password: String) async throws -> AuthResponse {
        try await authRequest(path: "/auth/signup", email: email, password: password)
    }

    private func authRequest(path: String, email: String, password: String) async throws -> AuthResponse {
        guard let url = URL(string: path, relativeTo: APIConfig.baseURL) else {
            throw ScanAPIError.invalidURL
        }
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try JSONEncoder().encode(["email": email, "password": password])

        let (data, response) = try await URLSession.shared.data(for: request)
        guard let http = response as? HTTPURLResponse else { throw ScanAPIError.badResponse }
        guard 200..<300 ~= http.statusCode else {
            // FastAPI renvoie {"detail": "..."} — on remonte ce message à l'UI.
            let detail = (try? JSONDecoder().decode([String: String].self, from: data))?["detail"]
            throw ScanAPIError.serverError(detail ?? "Authentication failed")
        }
        return try JSONDecoder().decode(AuthResponse.self, from: data)
    }
}

private extension Data {
    mutating func append(_ string: String) {
        append(Data(string.utf8))
    }

    mutating func appendMultipartField(name: String, value: String, boundary: String) {
        append("--\(boundary)\r\n")
        append("Content-Disposition: form-data; name=\"\(name)\"\r\n\r\n")
        append(value)
        append("\r\n")
    }
}
