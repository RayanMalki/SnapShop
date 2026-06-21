import AVFoundation
import Foundation
import Speech

@MainActor
final class VoiceCommandManager: ObservableObject {
    @Published private(set) var transcript = ""
    @Published private(set) var isListening = false
    @Published private(set) var audioInputName = "iPhone microphone"
    @Published private(set) var isUsingGlassesMicrophone = false

    private var recognizer: SFSpeechRecognizer?
    private let audioEngine = AVAudioEngine()
    private var recognitionRequest: SFSpeechAudioBufferRecognitionRequest?
    private var recognitionTask: SFSpeechRecognitionTask?
    private var listenContinuation: CheckedContinuation<String, Error>?
    private var listenTimeoutTask: Task<Void, Never>?

    init() {
        recognizer = Self.bestAvailableRecognizer()
    }

    /// Prefer the device language, then French, then English.
    private static func bestAvailableRecognizer() -> SFSpeechRecognizer? {
        let candidates = ([
            Locale.preferredLanguages.first,
            Locale.current.identifier,
            "fr-FR", 
            "fr_CA",
            "en-US",
            "en-GB",
        ] as [String?]).compactMap { $0 }

        var seen = Set<String>()
        for id in candidates {
            guard !seen.contains(id), let r = SFSpeechRecognizer(locale: Locale(identifier: id)), r.isAvailable else {
                continue
            }
            seen.insert(id)
            return r
        }
        return SFSpeechRecognizer()
    }

    func requestPermissions() async throws {
        let speechStatus = await withCheckedContinuation { continuation in
            SFSpeechRecognizer.requestAuthorization { status in
                continuation.resume(returning: status)
            }
        }
        guard speechStatus == .authorized else {
            throw VoiceCommandError.speechPermissionDenied
        }

        let audioStatus = await AVCaptureDevice.requestAccess(for: .audio)
        guard audioStatus else {
            throw VoiceCommandError.microphonePermissionDenied
        }
    }

    /// Listen until the user pauses (final result), or ``maxSeconds`` elapses.
    func listenFor(maxSeconds: TimeInterval = 6) async throws -> String {
        stopListening()
        listenTimeoutTask?.cancel()

        guard let recognizer, recognizer.isAvailable else {
            throw VoiceCommandError.recognizerUnavailable
        }

        return try await withCheckedThrowingContinuation { continuation in
            listenContinuation = continuation
            do {
                try startListeningInternal(recognizer: recognizer)
            } catch {
                listenContinuation = nil
                continuation.resume(throwing: error)
                return
            }

            listenTimeoutTask = Task {
                try? await Task.sleep(nanoseconds: UInt64(maxSeconds * 1_000_000_000))
                await finishListening(with: transcript)
            }
        }
    }

    func startListening() throws {
        stopListening()
        guard let recognizer, recognizer.isAvailable else {
            throw VoiceCommandError.recognizerUnavailable
        }
        try startListeningInternal(recognizer: recognizer)
    }

    private func startListeningInternal(recognizer: SFSpeechRecognizer) throws {
        transcript = ""
        try configureAudioInput()

        let request = SFSpeechAudioBufferRecognitionRequest()
        request.shouldReportPartialResults = true
        recognitionRequest = request

        let inputNode = audioEngine.inputNode
        let recordingFormat = inputNode.outputFormat(forBus: 0)
        inputNode.removeTap(onBus: 0)
        inputNode.installTap(onBus: 0, bufferSize: 1024, format: recordingFormat) { buffer, _ in
            request.append(buffer)
        }

        audioEngine.prepare()
        try audioEngine.start()
        isListening = true

        recognitionTask = recognizer.recognitionTask(with: request) { [weak self] result, error in
            Task { @MainActor in
                guard let self else { return }
                if let result {
                    self.transcript = result.bestTranscription.formattedString
                    if result.isFinal {
                        await self.finishListening(with: self.transcript)
                    }
                }
                if error != nil {
                    await self.finishListening(with: self.transcript)
                }
            }
        }
    }

    /// Route speech capture through the glasses' Bluetooth HFP microphone when
    /// it is available. Meta exposes microphone audio through the normal iOS
    /// audio route rather than through MWDATCamera.
    private func configureAudioInput() throws {
        let session = AVAudioSession.sharedInstance()

        do {
            try session.setCategory(
                .playAndRecord,
                mode: .voiceChat,
                options: [.allowBluetoothHFP]
            )
            try session.setActive(true)

            let availableInputs = session.availableInputs ?? []
            let hfpInputs = availableInputs.filter { $0.portType == .bluetoothHFP }
            let namedGlassesInput = hfpInputs.first { Self.looksLikeMetaGlasses($0.portName) }
            // Some firmware/iOS combinations expose a generic HFP name. It is
            // safe to select it when it is the only Bluetooth microphone.
            let glassesInput = namedGlassesInput ?? (hfpInputs.count == 1 ? hfpInputs[0] : nil)

            if let glassesInput {
                try session.setPreferredInput(glassesInput)
                audioInputName = glassesInput.portName
                isUsingGlassesMicrophone = true
                return
            }

            // Keep voice scan usable when the glasses audio profile is not
            // connected, while making the fallback explicit to the UI.
            if let builtInMic = availableInputs.first(where: { $0.portType == .builtInMic }) {
                try session.setPreferredInput(builtInMic)
                audioInputName = builtInMic.portName
            } else {
                try session.setPreferredInput(nil)
                audioInputName = session.currentRoute.inputs.first?.portName ?? "iPhone microphone"
            }
            isUsingGlassesMicrophone = false
        } catch {
            throw VoiceCommandError.audioSessionConfigurationFailed(error.localizedDescription)
        }
    }

    private static func looksLikeMetaGlasses(_ portName: String) -> Bool {
        let name = portName.lowercased()
        return name.contains("ray-ban")
            || name.contains("rayban")
            || name.contains("meta")
            || name.contains("oakley")
    }

    private func finishListening(with text: String) async {
        listenTimeoutTask?.cancel()
        listenTimeoutTask = nil
        let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
        stopListening()
        if let continuation = listenContinuation {
            listenContinuation = nil
            continuation.resume(returning: trimmed)
        }
    }

    func stopListening() {
        listenTimeoutTask?.cancel()
        listenTimeoutTask = nil
        if audioEngine.isRunning {
            audioEngine.stop()
        }
        audioEngine.inputNode.removeTap(onBus: 0)
        recognitionRequest?.endAudio()
        recognitionRequest = nil
        recognitionTask?.cancel()
        recognitionTask = nil
        isListening = false
        try? AVAudioSession.sharedInstance().setActive(
            false,
            options: .notifyOthersOnDeactivation
        )
    }
}

enum VoiceCommandError: LocalizedError {
    case speechPermissionDenied
    case microphonePermissionDenied
    case recognizerUnavailable
    case audioSessionConfigurationFailed(String)

    var errorDescription: String? {
        switch self {
        case .speechPermissionDenied:
            return "Allow speech recognition in Settings."
        case .microphonePermissionDenied:
            return "Allow microphone access in Settings."
        case .recognizerUnavailable:
            return "Speech recognition isn't available."
        case .audioSessionConfigurationFailed(let message):
            return "Could not use the glasses microphone. Details: \(message)"
        }
    }
}
