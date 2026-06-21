import Foundation
import UIKit

#if canImport(MWDATCore) && canImport(MWDATCamera)
import MWDATCamera
import MWDATCore
#endif

@MainActor
final class MetaGlassesManager: ObservableObject {
    @Published private(set) var statusText = "Glasses not connected"
    @Published private(set) var isStreaming = false
    @Published private(set) var needsRegistration = false

    #if canImport(MWDATCore) && canImport(MWDATCamera)
    private let wearables = Wearables.shared
    private var deviceSession: DeviceSession?
    private var registrationListenerTask: Task<Void, Never>?
    private var deviceListenerTask: Task<Void, Never>?
    private var stream: MWDATCamera.Stream?
    private var stateListenerToken: AnyListenerToken?
    private var errorListenerToken: AnyListenerToken?
    private var videoFrameListenerToken: AnyListenerToken?
    private var photoDataListenerToken: AnyListenerToken?
    private var photoContinuation: CheckedContinuation<Data, Error>?
    private var latestVideoFrameJPEG: Data?
    private var lastVideoFrameJPEGAt = Date.distantPast
    private let photoCaptureTimeoutNanoseconds: UInt64 = 12_000_000_000
    #endif

    init() {
        #if canImport(MWDATCore) && canImport(MWDATCamera)
        needsRegistration = wearables.registrationState != .registered
        statusText = needsRegistration ? "Register SnapShop with Meta AI" : "Glasses registered"

        registrationListenerTask = Task { [weak self] in
            for await state in Wearables.shared.registrationStateStream() {
                await MainActor.run {
                    self?.handleRegistrationState(state)
                }
            }
        }

        deviceListenerTask = Task { [weak self] in
            for await devices in Wearables.shared.devicesStream() {
                await MainActor.run {
                    self?.handleDevices(devices)
                }
            }
        }
        #endif
    }

    deinit {
        #if canImport(MWDATCore) && canImport(MWDATCamera)
        registrationListenerTask?.cancel()
        deviceListenerTask?.cancel()
        #endif
    }

    func registerWithMetaAI() async {
        #if canImport(MWDATCore)
        if Wearables.shared.registrationState == .registered {
            needsRegistration = false
            handleDevices(Wearables.shared.devices)
            return
        }

        do {
            statusText = "Opening Meta AI registration"
            try await Wearables.shared.startRegistration()
        } catch let error as RegistrationError {
            if error.description.localizedCaseInsensitiveContains("already registered") {
                needsRegistration = false
                handleDevices(Wearables.shared.devices)
            } else {
                statusText = "Registration failed: \(error.description)"
            }
        } catch {
            if error.localizedDescription.localizedCaseInsensitiveContains("already registered") {
                needsRegistration = false
                handleDevices(Wearables.shared.devices)
            } else {
                statusText = "Registration failed: \(error.localizedDescription)"
            }
        }
        #else
        statusText = "Meta DAT SDK is not linked"
        #endif
    }

    func capturePhoto() async throws -> Data {
        #if canImport(MWDATCore) && canImport(MWDATCamera)
        try await ensureStreaming()
        guard let stream else {
            throw MetaGlassesError.streamUnavailable
        }

        statusText = "Capturing from glasses"
        return try await withCheckedThrowingContinuation { continuation in
            if let existingContinuation = photoContinuation {
                existingContinuation.resume(throwing: MetaGlassesError.captureFailed)
            }
            photoContinuation = continuation
            let didStart = stream.capturePhoto(format: .jpeg)
            if !didStart {
                photoContinuation = nil
                continuation.resume(throwing: MetaGlassesError.captureFailed)
                return
            }

            let timeout = photoCaptureTimeoutNanoseconds
            Task { [weak self] in
                guard let self else { return }
                try? await Task.sleep(nanoseconds: timeout)
                await MainActor.run {
                    guard let pendingContinuation = self.photoContinuation else {
                        return
                    }
                    self.photoContinuation = nil
                    if let fallbackFrame = self.latestVideoFrameJPEG {
                        self.statusText = "Using glasses video frame"
                        pendingContinuation.resume(returning: fallbackFrame)
                    } else {
                        self.statusText = "Photo capture timed out"
                        pendingContinuation.resume(throwing: MetaGlassesError.captureTimeout)
                    }
                }
            }
        }
        #else
        throw MetaGlassesError.sdkUnavailable
        #endif
    }

    func stop() async {
        #if canImport(MWDATCore) && canImport(MWDATCamera)
        let activeStream = stream
        stream = nil
        clearListeners()
        latestVideoFrameJPEG = nil
        lastVideoFrameJPEGAt = .distantPast
        isStreaming = false
        statusText = "Glasses stream stopped"
        await activeStream?.stop()
        deviceSession?.stop()
        deviceSession = nil
        #endif
    }

    #if canImport(MWDATCore) && canImport(MWDATCamera)
    private func handleRegistrationState(_ state: RegistrationState) {
        needsRegistration = state != .registered
        switch state {
        case .registered:
            handleDevices(wearables.devices)
        case .registering:
            statusText = "Finish approval in Meta AI"
        case .available:
            statusText = "Register SnapShop with Meta AI"
        case .unavailable:
            statusText = "Meta AI registration is unavailable"
        @unknown default:
            statusText = "Check Meta AI registration"
        }
    }

    private func handleDevices(_ devices: [DeviceIdentifier]) {
        guard wearables.registrationState == .registered else { return }

        if devices.isEmpty {
            statusText = "Registered, but no DAT glasses are visible yet"
            return
        }

        let summaries = devices.compactMap { identifier -> String? in
            guard let device = wearables.deviceForIdentifier(identifier) else {
                return nil
            }
            let compatibility = device.compatibility()
            return "\(device.nameOrId()) (\(compatibility))"
        }

        if summaries.isEmpty {
            statusText = "Registered. Waiting for glasses details."
        } else {
            statusText = "Detected: \(summaries.joined(separator: ", "))"
        }
    }

    private func ensureStreaming() async throws {
        if isStreaming, stream != nil {
            return
        }

        guard wearables.registrationState == .registered else {
            needsRegistration = true
            statusText = "Tap Register, then approve SnapShop in Meta AI"
            throw MetaGlassesError.registrationRequired
        }

        let selector = AutoDeviceSelector(wearables: wearables)
        try await waitForActiveDevice(using: selector)

        statusText = "Checking camera permission"
        let permissionStatus: PermissionStatus
        do {
            var status = try await wearables.checkPermissionStatus(.camera)
            if status != .granted {
                statusText = "Approve camera access in Meta AI"
                status = try await wearables.requestPermission(.camera)
            }
            permissionStatus = status
        } catch let error as PermissionError {
            statusText = "Meta camera permission is not granted"
            throw MetaGlassesError.permissionRequestFailed(error.description)
        } catch {
            statusText = "Meta camera permission is not granted"
            throw MetaGlassesError.permissionRequestFailed(error.localizedDescription)
        }
        guard permissionStatus == .granted else {
            throw MetaGlassesError.permissionDenied
        }

        statusText = "Looking for eligible glasses"
        let session = try await startedDeviceSession(using: selector)

        let config = StreamConfiguration(
            videoCodec: VideoCodec.raw,
            resolution: StreamingResolution.low,
            frameRate: 15
        )
        guard let newStream = try? session.addStream(config: config) else {
            throw MetaGlassesError.streamUnavailable
        }

        stream = newStream
        setupListeners(for: newStream)
        statusText = "Starting glasses camera"
        await newStream.start()
        try await Task.sleep(nanoseconds: 1_500_000_000)
        isStreaming = newStream.state == .streaming
        if isStreaming {
            statusText = "Glasses ready"
        } else {
            statusText = "Waiting for glasses camera"
            throw MetaGlassesError.streamTimeout
        }
    }

    private func startedDeviceSession(using selector: AutoDeviceSelector) async throws -> DeviceSession {
        if let deviceSession, deviceSession.state == .started {
            return deviceSession
        }

        let session: DeviceSession
        do {
            session = try wearables.createSession(deviceSelector: selector)
        } catch DeviceSessionError.noEligibleDevice {
            statusText = "No eligible DAT glasses found"
            throw MetaGlassesError.noEligibleDevice
        } catch DeviceSessionError.datAppOnTheGlassesUpdateRequired {
            statusText = "Update the app on your glasses"
            throw MetaGlassesError.datAppUpdateRequired
        } catch {
            statusText = "Could not create glasses session"
            throw error
        }
        deviceSession = session

        let states = session.stateStream()
        let errors = session.errorStream()
        try session.start()

        if session.state == .started {
            return session
        }

        try await withThrowingTaskGroup(of: Void.self) { group in
            group.addTask {
                for await state in states {
                    if state == .started { return }
                    if state == .stopped {
                        throw MetaGlassesError.sessionFailed
                    }
                }
                throw MetaGlassesError.sessionFailed
            }
            group.addTask {
                for await error in errors {
                    if error == .datAppOnTheGlassesUpdateRequired {
                        throw MetaGlassesError.datAppUpdateRequired
                    }
                    throw error
                }
                throw MetaGlassesError.sessionFailed
            }
            _ = try await group.next()
            group.cancelAll()
        }

        return session
    }

    private func waitForActiveDevice(using selector: AutoDeviceSelector) async throws {
        statusText = "Waiting for DAT glasses to become active"

        try await withThrowingTaskGroup(of: Void.self) { group in
            group.addTask {
                for await device in selector.activeDeviceStream() {
                    if device != nil {
                        return
                    }
                }
                throw MetaGlassesError.noEligibleDevice
            }

            group.addTask {
                try await Task.sleep(nanoseconds: 8_000_000_000)
                throw MetaGlassesError.noEligibleDevice
            }

            _ = try await group.next()
            group.cancelAll()
        }
    }

    private func setupListeners(for stream: MWDATCamera.Stream) {
        clearListeners()

        stateListenerToken = stream.statePublisher.listen { [weak self] state in
            Task { @MainActor in
                guard let self else { return }
                self.isStreaming = state == .streaming
                if state == .streaming {
                    self.statusText = "Glasses ready"
                } else if state == .stopped || state == .stopping {
                    self.stream = nil
                    self.isStreaming = false
                    if let pendingContinuation = self.photoContinuation {
                        self.photoContinuation = nil
                        if let fallbackFrame = self.latestVideoFrameJPEG {
                            self.statusText = "Using glasses video frame"
                            pendingContinuation.resume(returning: fallbackFrame)
                        } else {
                            self.statusText = "Glasses stream stopped"
                            pendingContinuation.resume(throwing: MetaGlassesError.streamTimeout)
                        }
                    }
                }
            }
        }

        errorListenerToken = stream.errorPublisher.listen { [weak self] error in
            Task { @MainActor in
                guard let self else { return }
                self.statusText = error.localizedDescription
                if let pendingContinuation = self.photoContinuation {
                    self.photoContinuation = nil
                    if let fallbackFrame = self.latestVideoFrameJPEG {
                        self.statusText = "Using glasses video frame"
                        pendingContinuation.resume(returning: fallbackFrame)
                    } else {
                        pendingContinuation.resume(throwing: error)
                    }
                }
                self.stream = nil
                self.isStreaming = false
            }
        }

        videoFrameListenerToken = stream.videoFramePublisher.listen { [weak self] frame in
            let image = frame.makeUIImage()
            let data = image?.jpegData(compressionQuality: 0.9)
            Task { @MainActor in
                guard let self, let data else { return }
                let now = Date()
                guard now.timeIntervalSince(self.lastVideoFrameJPEGAt) >= 0.75 else {
                    return
                }
                self.latestVideoFrameJPEG = data
                self.lastVideoFrameJPEGAt = now
            }
        }

        photoDataListenerToken = stream.photoDataPublisher.listen { [weak self] photoData in
            Task { @MainActor in
                self?.statusText = "Photo captured"
                self?.photoContinuation?.resume(returning: photoData.data)
                self?.photoContinuation = nil
            }
        }
    }

    private func clearListeners() {
        stateListenerToken = nil
        errorListenerToken = nil
        videoFrameListenerToken = nil
        photoDataListenerToken = nil
    }
    #endif
}

enum MetaGlassesError: LocalizedError {
    case sdkUnavailable
    case registrationRequired
    case noEligibleDevice
    case datAppUpdateRequired
    case permissionDenied
    case permissionRequestFailed(String)
    case sessionFailed
    case streamUnavailable
    case streamTimeout
    case captureTimeout
    case captureFailed

    var errorDescription: String? {
        switch self {
        case .sdkUnavailable:
            return "Meta DAT SDK is not linked to this build."
        case .registrationRequired:
            return "SnapShop is not registered with Meta AI yet. Tap Register, approve SnapShop in Meta AI, then return and try Voice scan again."
        case .noEligibleDevice:
            return "No eligible DAT glasses are active. In Meta AI, make sure Developer Mode is enabled for this glasses pair, the glasses are worn/open and nearby, then wait a few seconds and try again."
        case .datAppUpdateRequired:
            return "The app on the glasses needs an update before DAT camera access can start. Open Meta AI and update the glasses app, then try again."
        case .permissionDenied:
            return "Meta camera permission was denied. Tap Register or approve camera access in Meta AI, then try again."
        case .permissionRequestFailed(let message):
            return "Meta camera permission could not be requested. Open Meta AI, make sure Developer Mode is enabled for the glasses, approve SnapShop camera access, then try again. Details: \(message)"
        case .sessionFailed:
            return "Could not start a glasses session."
        case .streamUnavailable:
            return "The glasses camera stream is unavailable."
        case .streamTimeout:
            return "The glasses camera did not start in time."
        case .captureTimeout:
            return "The glasses did not return a photo. Make sure the glasses are awake, keep the app open, then try Voice scan again."
        case .captureFailed:
            return "The glasses did not capture a photo."
        }
    }
}
