"""Voice Support - Speech-to-Text and Text-to-Speech for IO.

Provides:
- Speech-to-text (STT) for voice input
- Text-to-speech (TTS) for voice output
- Voice commands and hotwords
- Audio recording and playback
"""

from __future__ import annotations

import asyncio
import io
import wave
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Callable


class VoiceCommand(Enum):
    """Voice commands that can be recognized."""

    START = "start"
    STOP = "stop"
    EXPLAIN = "explain"
    FIX = "fix"
    TEST = "test"
    SAVE = "save"
    UNDO = "undo"


@dataclass
class VoiceConfig:
    """Configuration for voice support."""

    stt_engine: str = "whisper"  # whisper, google, azure
    tts_engine: str = "system"  # system, google, azure, elevenlabs
    language: str = "en"
    hotword: str = "hey io"
    sensitivity: float = 0.5
    auto_start: bool = False


class SpeechToText:
    """Speech-to-text engine."""

    def __init__(self, config: VoiceConfig):
        self.config = config
        self._recording = False
        self._audio_buffer: list[bytes] = []

    async def start_recording(self) -> None:
        """Start recording audio."""
        self._recording = True
        self._audio_buffer = []

        # Platform-specific recording
        import sys

        if sys.platform == "darwin":  # macOS
            await self._start_macos_recording()
        elif sys.platform == "linux":
            await self._start_linux_recording()
        elif sys.platform == "win32":
            await self._start_windows_recording()

    async def stop_recording(self) -> bytes:
        """Stop recording and return audio data."""
        self._recording = False

        # Combine all audio chunks
        audio_data = b"".join(self._audio_buffer)

        # Convert to WAV format
        wav_buffer = io.BytesIO()
        with wave.open(wav_buffer, "wb") as wav_file:
            wav_file.setnchannels(1)  # Mono
            wav_file.setsampwidth(2)  # 16-bit
            wav_file.setframerate(16000)  # 16kHz
            wav_file.writeframes(audio_data)

        return wav_buffer.getvalue()

    async def _start_macos_recording(self) -> None:
        """Start recording on macOS using sox or avrecorder."""
        import subprocess

        process = subprocess.Popen(
            ["rec", "-t", "wav", "-r", "16000", "-c", "1", "-b", "16", "-"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        # Read chunks while recording
        while self._recording:
            chunk = process.stdout.read(1024)
            if chunk:
                self._audio_buffer.append(chunk)
            await asyncio.sleep(0.01)

        process.terminate()

    async def _start_linux_recording(self) -> None:
        """Start recording on Linux using arecord."""
        import subprocess

        process = subprocess.Popen(
            ["arecord", "-f", "S16_LE", "-r", "16000", "-c", "1", "-"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        while self._recording:
            chunk = process.stdout.read(1024)
            if chunk:
                self._audio_buffer.append(chunk)
            await asyncio.sleep(0.01)

        process.terminate()

    async def _start_windows_recording(self) -> None:
        """Start recording on Windows."""
        # Would use pyaudio or similar
        pass

    async def transcribe(self, audio_data: bytes) -> str:
        """Transcribe audio to text."""
        if self.config.stt_engine == "whisper":
            return await self._transcribe_whisper(audio_data)
        elif self.config.stt_engine == "google":
            return await self._transcribe_google(audio_data)
        else:
            raise ValueError(f"Unknown STT engine: {self.config.stt_engine}")

    async def _transcribe_whisper(self, audio_data: bytes) -> str:
        """Transcribe using OpenAI Whisper."""
        try:
            import openai

            # Save to temporary file
            temp_path = Path("/tmp/io_voice_input.wav")
            temp_path.write_bytes(audio_data)

            with open(temp_path, "rb") as audio_file:
                transcript = openai.audio.transcriptions.create(
                    model="whisper-1", file=audio_file, language=self.config.language
                )

            temp_path.unlink()
            return transcript.text
        except ImportError:
            raise ImportError("openai package required for Whisper STT")

    async def _transcribe_google(self, audio_data: bytes) -> str:
        """Transcribe using Google Speech Recognition."""
        try:
            import speech_recognition as sr

            recognizer = sr.Recognizer()
            audio = sr.AudioFile(io.BytesIO(audio_data))

            with audio as source:
                audio_data = recognizer.record(source)

            return recognizer.recognize_google(audio_data, language=self.config.language)
        except ImportError:
            raise ImportError("speech_recognition package required for Google STT")


class TextToSpeech:
    """Text-to-speech engine."""

    def __init__(self, config: VoiceConfig):
        self.config = config

    async def speak(self, text: str) -> None:
        """Speak text aloud."""
        if self.config.tts_engine == "system":
            await self._speak_system(text)
        elif self.config.tts_engine == "elevenlabs":
            await self._speak_elevenlabs(text)
        elif self.config.tts_engine == "google":
            await self._speak_google(text)

    async def _speak_system(self, text: str) -> None:
        """Use system TTS."""
        import subprocess
        import sys

        if sys.platform == "darwin":  # macOS
            subprocess.run(["say", text], check=True)
        elif sys.platform == "linux":
            subprocess.run(["espeak", text], check=True)
        elif sys.platform == "win32":
            # Would use pyttsx3 or similar
            pass

    async def _speak_elevenlabs(self, text: str) -> None:
        """Use ElevenLabs TTS."""
        try:
            import aiohttp

            api_key = "your_api_key"  # Would get from config
            voice_id = "21m00Tcm4TlvDq8ikWAM"  # Default voice

            url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"

            headers = {
                "Accept": "audio/mpeg",
                "Content-Type": "application/json",
                "xi-api-key": api_key,
            }

            data = {
                "text": text,
                "model_id": "eleven_monolingual_v1",
                "voice_settings": {"stability": 0.5, "similarity_boost": 0.5},
            }

            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=data, headers=headers) as response:
                    if response.status == 200:
                        audio_data = await response.read()
                        # Play audio
                        await self._play_audio(audio_data)
        except ImportError:
            raise ImportError("aiohttp package required for ElevenLabs TTS")

    async def _speak_google(self, text: str) -> None:
        """Use Google TTS."""
        try:
            from gtts import gTTS
            import tempfile
            import os

            tts = gTTS(text=text, lang=self.config.language)

            with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as fp:
                tts.save(fp.name)
                temp_path = fp.name

            # Play the audio
            import subprocess

            if os.path.exists(temp_path):
                subprocess.run(["afplay", temp_path], check=True)
                os.unlink(temp_path)
        except ImportError:
            raise ImportError("gtts package required for Google TTS")

    async def _play_audio(self, audio_data: bytes) -> None:
        """Play audio data."""
        import subprocess
        import tempfile
        import os

        # Save to temp file and play
        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as f:
            f.write(audio_data)
            temp_path = f.name

        try:
            subprocess.run(["afplay", temp_path], check=True)
        finally:
            os.unlink(temp_path)


class VoiceCommandRecognizer:
    """Recognize voice commands from transcribed text."""

    COMMAND_PATTERNS = {
        VoiceCommand.START: ["start", "begin", "go", "run"],
        VoiceCommand.STOP: ["stop", "halt", "end", "finish"],
        VoiceCommand.EXPLAIN: ["explain", "what is", "what does", "describe"],
        VoiceCommand.FIX: ["fix", "repair", "correct", "solve"],
        VoiceCommand.TEST: ["test", "check", "validate"],
        VoiceCommand.SAVE: ["save", "store", "write"],
        VoiceCommand.UNDO: ["undo", "revert", "cancel"],
    }

    def recognize(self, text: str) -> tuple[VoiceCommand | None, str]:
        """Recognize command and extract argument."""
        text_lower = text.lower()

        for command, patterns in self.COMMAND_PATTERNS.items():
            for pattern in patterns:
                if pattern in text_lower:
                    # Extract argument (text after the command)
                    idx = text_lower.find(pattern)
                    if idx >= 0:
                        argument = text[idx + len(pattern) :].strip()
                        return command, argument

        return None, text


class VoiceManager:
    """Manages voice input/output for IO."""

    def __init__(self, config: VoiceConfig | None = None):
        self.config = config or VoiceConfig()
        self.stt = SpeechToText(self.config)
        self.tts = TextToSpeech(self.config)
        self.command_recognizer = VoiceCommandRecognizer()

        self._listening = False
        self._hotword_detector: Any = None
        self._command_handlers: dict[VoiceCommand, Callable] = {}

    def register_command_handler(self, command: VoiceCommand, handler: Callable) -> None:
        """Register a handler for a voice command."""
        self._command_handlers[command] = handler

    async def start_listening(self) -> None:
        """Start listening for voice input."""
        self._listening = True

        while self._listening:
            try:
                # Record audio
                await self.stt.start_recording()
                await asyncio.sleep(5)  # Record for 5 seconds
                audio_data = await self.stt.stop_recording()

                # Transcribe
                text = await self.stt.transcribe(audio_data)

                if text:
                    # Check for hotword if configured
                    if self.config.hotword and self.config.hotword not in text.lower():
                        continue

                    # Recognize command
                    command, argument = self.command_recognizer.recognize(text)

                    if command and command in self._command_handlers:
                        await self._command_handlers[command](argument)
                    else:
                        # Treat as regular chat input
                        if VoiceCommand.START in self._command_handlers:
                            await self._command_handlers[VoiceCommand.START](text)

            except Exception as e:
                print(f"Voice error: {e}")
                await asyncio.sleep(1)

    def stop_listening(self) -> None:
        """Stop listening for voice input."""
        self._listening = False

    async def speak(self, text: str) -> None:
        """Speak text aloud."""
        await self.tts.speak(text)

    async def listen_once(self) -> str:
        """Listen for one utterance and return text."""
        await self.stt.start_recording()
        await asyncio.sleep(3)
        audio_data = await self.stt.stop_recording()
        return await self.stt.transcribe(audio_data)
