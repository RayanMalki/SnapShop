import Foundation

enum APIConfig {
    /// Mac running uvicorn — use LAN IP for physical iPhone: `ipconfig getifaddr en0`
    static let baseURL = URL(string: "http://10.201.48.126:8000")!
}
