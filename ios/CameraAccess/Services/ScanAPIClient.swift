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
