import Foundation

enum APIConfig {
    /// Mac running uvicorn — use LAN IP for physical iPhone: `ipconfig getifaddr en0`
    static let baseURL = URL(string: "http://localhost:8000")!
}
