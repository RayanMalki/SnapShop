import AVFoundation
import Foundation
import Speech

@MainActor
final class VoiceCommandManager: ObservableObject {
    @Published private(set) var transcript = ""
    @Published private(set) var isListening = false

    private let recognizer = SFSpeechRecognizer(locale: Locale(identifier: "en_US"))
    private let audioEngine = AVAudioEngine()
    private var recognitionRequest: SFSpeechAudioBufferRecognitionRequest?
    private var recognitionTask: SFSpeechRecognitionTask?

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

    func startListening() throws {
        stopListening()

        guard let recognizer, recognizer.isAvailable else {
            throw VoiceCommandError.recognizerUnavailable
        }

        transcript = ""

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
                if let result {
                    self?.transcript = result.bestTranscription.formattedString
                }
                if error != nil || result?.isFinal == true {
                    self?.stopListening()
                }
            }
        }
    }

    func stopListening() {
        if audioEngine.isRunning {
            audioEngine.stop()
        }
        audioEngine.inputNode.removeTap(onBus: 0)
        recognitionRequest?.endAudio()
        recognitionRequest = nil
        recognitionTask?.cancel()
        recognitionTask = nil
        isListening = false
    }
}

enum VoiceCommandError: LocalizedError {
    case speechPermissionDenied
    case microphonePermissionDenied
    case recognizerUnavailable

    var errorDescription: String? {
        switch self {
        case .speechPermissionDenied:
            return "Speech recognition permission is required."
        case .microphonePermissionDenied:
            return "Microphone permission is required."
        case .recognizerUnavailable:
            return "Speech recognition is not available right now."
        }
    }
}
