"""Voice integration tools for speech-to-text (STT) and text-to-speech (TTS).

This module provides tools for voice interaction with IO, enabling hands-free
operation through speech recognition and audio feedback.
"""

from __future__ import annotations

import asyncio
import io
import json
import logging
import os
import subprocess
import sys
import tempfile
import time
import wave
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from io_agent import GLOBAL_TOOL_REGISTRY, Tool, ToolContext, ToolResult

from ..config import load_config

logger = logging.getLogger(__name__)

# Voice state management
_voice_state: dict[str, Any] = {
    "recording": False,
    "transcribing": False,
    "speaking": False,
    "last_recording_path": None,
    "stt_provider": "whisper",  # whisper, whisper-api, azure, gcp
    "tts_provider": "system",  # system, openai, azure, gcp, elevenlabs
    "voice_enabled": False,
    "auto_tts": False,  # Auto-read responses
}

_state_lock = asyncio.Lock()


@dataclass
class RecordingSession:
    """Active recording session."""

    start_time: float = field(default_factory=time.monotonic)
    duration: float = 0.0
    audio_path: str | None = None
    sample_rate: int = 16000
    channels: int = 1


@dataclass
class TranscriptionResult:
    """STT transcription result."""

    text: str
    confidence: float
    language: str | None = None
    duration: float = 0.0
    word_timings: list[dict[str, Any]] | None = None


class VoiceRecordTool(Tool):
    """Record audio from microphone for voice input."""

    name = "voice_record"
    description = (
        "Record audio from the microphone for voice input. "
        "Use duration to specify recording length in seconds (default: 5). "
        "Use 'start' to begin recording without duration (requires 'stop' to end)."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["start", "stop", "record"],
                "description": "Action to perform: start recording, stop recording, or record for a duration",
                "default": "record",
            },
            "duration": {
                "type": "integer",
                "description": "Recording duration in seconds (for 'record' action)",
                "minimum": 1,
                "maximum": 300,
                "default": 5,
            },
            "sample_rate": {
                "type": "integer",
                "description": "Audio sample rate in Hz",
                "default": 16000,
            },
        },
        "required": [],
    }

    async def execute(self, context: ToolContext, arguments: dict[str, object]) -> ToolResult:
        action = str(arguments.get("action", "record"))

        if action == "start":
            return await _start_recording(context)
        elif action == "stop":
            return await _stop_recording(context)
        else:  # record
            duration = int(arguments.get("duration", 5))
            return await _record_fixed_duration(duration, context)


class VoiceTranscribeTool(Tool):
    """Transcribe recorded audio to text using STT."""

    name = "voice_transcribe"
    description = (
        "Transcribe audio to text using speech-to-text (STT). "
        "Can transcribe the last recording or a specific audio file. "
        "Uses OpenAI Whisper by default, or configured STT provider."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "audio_path": {
                "type": "string",
                "description": "Path to audio file to transcribe (uses last recording if not provided)",
            },
            "language": {
                "type": "string",
                "description": "Language code (e.g., 'en', 'es', 'fr'). Auto-detect if not provided.",
            },
            "provider": {
                "type": "string",
                "enum": ["whisper", "whisper-api", "azure", "gcp", "local"],
                "description": "STT provider to use (default: whisper)",
            },
        },
        "required": [],
    }

    async def execute(self, context: ToolContext, arguments: dict[str, object]) -> ToolResult:
        audio_path = arguments.get("audio_path")
        language = arguments.get("language")
        provider = arguments.get("provider", "whisper")

        return await _transcribe_audio(audio_path, str(provider), language, context)


class VoiceSpeakTool(Tool):
    """Convert text to speech using TTS."""

    name = "voice_speak"
    description = (
        "Convert text to speech using text-to-speech (TTS). "
        "Reads the provided text aloud using the configured voice."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "text": {
                "type": "string",
                "description": "Text to speak",
            },
            "voice": {
                "type": "string",
                "description": "Voice to use (provider-specific)",
            },
            "speed": {
                "type": "number",
                "description": "Speech speed multiplier (0.5-2.0)",
                "minimum": 0.5,
                "maximum": 2.0,
                "default": 1.0,
            },
            "provider": {
                "type": "string",
                "enum": ["system", "openai", "azure", "gcp", "elevenlabs"],
                "description": "TTS provider to use (default: system)",
            },
        },
        "required": ["text"],
    }

    async def execute(self, context: ToolContext, arguments: dict[str, object]) -> ToolResult:
        text = str(arguments["text"])
        voice = arguments.get("voice")
        speed = float(arguments.get("speed", 1.0))
        provider = arguments.get("provider", "system")

        return await _speak_text(text, voice, speed, str(provider), context)


class VoiceStatusTool(Tool):
    """Get voice system status and configuration."""

    name = "voice_status"
    description = (
        "Get the current voice system status including STT/TTS providers, "
        "recording state, and available voices."
    )
    input_schema = {
        "type": "object",
        "properties": {},
    }

    async def execute(self, context: ToolContext, arguments: dict[str, object]) -> ToolResult:
        return await _get_voice_status(context)


class VoiceConfigTool(Tool):
    """Configure voice settings (STT/TTS providers, voices, auto-TTS)."""

    name = "voice_config"
    description = (
        "Configure voice system settings including STT/TTS providers, "
        "voice selection, and automatic speech output."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "stt_provider": {
                "type": "string",
                "enum": ["whisper", "whisper-api", "azure", "gcp", "local"],
                "description": "Speech-to-text provider",
            },
            "tts_provider": {
                "type": "string",
                "enum": ["system", "openai", "azure", "gcp", "elevenlabs"],
                "description": "Text-to-speech provider",
            },
            "voice": {
                "type": "string",
                "description": "Default voice to use for TTS",
            },
            "auto_tts": {
                "type": "boolean",
                "description": "Automatically read responses aloud",
            },
            "enabled": {
                "type": "boolean",
                "description": "Enable/disable voice mode",
            },
        },
        "required": [],
    }

    async def execute(self, context: ToolContext, arguments: dict[str, object]) -> ToolResult:
        return await _configure_voice(arguments, context)


class VoiceListVoicesTool(Tool):
    """List available voices for TTS."""

    name = "voice_list_voices"
    description = "List all available voices for the configured TTS provider."
    input_schema = {
        "type": "object",
        "properties": {
            "provider": {
                "type": "string",
                "enum": ["system", "openai", "azure", "gcp", "elevenlabs"],
                "description": "TTS provider to list voices for (uses default if not provided)",
            },
        },
        "required": [],
    }

    async def execute(self, context: ToolContext, arguments: dict[str, object]) -> ToolResult:
        provider = arguments.get("provider")
        return await _list_voices(provider, context)


# Helper functions


async def _start_recording(context: ToolContext) -> ToolResult:
    """Start a new recording session."""
    global _voice_state

    async with _state_lock:
        if _voice_state["recording"]:
            return ToolResult(
                content="Already recording. Use 'voice_record action=stop' to end.",
                is_error=True,
            )

        _voice_state["recording"] = True
        _voice_state["current_session"] = RecordingSession()

    return ToolResult(
        content="🎤 Recording started. Use 'voice_record action=stop' to end recording."
    )


async def _stop_recording(context: ToolContext) -> ToolResult:
    """Stop the current recording session."""
    global _voice_state

    async with _state_lock:
        if not _voice_state["recording"]:
            return ToolResult(
                content="No recording in progress. Use 'voice_record action=start' to begin.",
                is_error=True,
            )

        _voice_state["recording"] = False
        session = _voice_state.get("current_session")

        if session:
            session.duration = time.monotonic() - session.start_time

    return ToolResult(
        content=f"⏹️ Recording stopped. Duration: {session.duration:.1f}s\n"
        "Use 'voice_transcribe' to convert to text."
    )


async def _record_fixed_duration(duration: int, context: ToolContext) -> ToolResult:
    """Record audio for a fixed duration."""
    global _voice_state

    try:
        # Create temp file for recording
        temp_dir = tempfile.gettempdir()
        audio_path = os.path.join(temp_dir, f"io_voice_{int(time.time())}.wav")

        # Try to record using available methods
        if await _record_with_sox(audio_path, duration):
            pass
        elif await _record_with_ffmpeg(audio_path, duration):
            pass
        elif await _record_with_avfoundation(audio_path, duration):
            pass
        else:
            return ToolResult(
                content="Could not record audio. Please install sox, ffmpeg, or ensure microphone access.",
                is_error=True,
            )

        async with _state_lock:
            _voice_state["last_recording_path"] = audio_path

        return ToolResult(
            content=f"🎤 Recorded {duration}s audio.\nUse 'voice_transcribe' to convert to text."
        )

    except Exception as e:
        return ToolResult(content=f"Recording error: {e}", is_error=True)


async def _record_with_sox(audio_path: str, duration: int) -> bool:
    """Record using sox (cross-platform)."""
    try:
        result = await asyncio.create_subprocess_exec(
            "sox",
            "-d",  # Default audio device
            "-r",
            "16000",  # Sample rate
            "-c",
            "1",  # Mono
            "-t",
            "wav",
            audio_path,
            "trim",
            "0",
            str(duration),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
        await result.wait()
        return result.returncode == 0 and os.path.exists(audio_path)
    except (FileNotFoundError, subprocess.SubprocessError):
        return False


async def _record_with_ffmpeg(audio_path: str, duration: int) -> bool:
    """Record using ffmpeg."""
    try:
        device = "default" if sys.platform != "darwin" else ":0"
        result = await asyncio.create_subprocess_exec(
            "ffmpeg",
            "-y",
            "-f",
            "avfoundation" if sys.platform == "darwin" else "alsa",
            "-i",
            device,
            "-t",
            str(duration),
            "-ar",
            "16000",
            "-ac",
            "1",
            audio_path,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
        await result.wait()
        return result.returncode == 0 and os.path.exists(audio_path)
    except (FileNotFoundError, subprocess.SubprocessError):
        return False


async def _record_with_avfoundation(audio_path: str, duration: int) -> bool:
    """Record using macOS AVFoundation."""
    if sys.platform != "darwin":
        return False

    try:
        # Try using say or other macOS tools
        result = await asyncio.create_subprocess_exec(
            "ffmpeg",
            "-y",
            "-f",
            "avfoundation",
            "-i",
            ":0",
            "-t",
            str(duration),
            "-ar",
            "16000",
            "-ac",
            "1",
            audio_path,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
        await result.wait()
        return result.returncode == 0 and os.path.exists(audio_path)
    except (FileNotFoundError, subprocess.SubprocessError):
        return False


async def _transcribe_audio(
    audio_path: object,
    provider: str,
    language: object,
    context: ToolContext,
) -> ToolResult:
    """Transcribe audio to text."""
    global _voice_state

    # Use last recording if no path provided
    if not audio_path:
        async with _state_lock:
            audio_path = _voice_state.get("last_recording_path")
        if not audio_path:
            return ToolResult(
                content="No audio file specified and no previous recording found.",
                is_error=True,
            )

    audio_file = str(audio_path)
    if not os.path.exists(audio_file):
        return ToolResult(content=f"Audio file not found: {audio_file}", is_error=True)

    # Try transcription providers
    if provider in ["whisper", "whisper-api"]:
        result = await _transcribe_with_whisper(audio_file, str(language) if language else None)
    elif provider == "local":
        result = await _transcribe_local(audio_file, str(language) if language else None)
    else:
        result = await _transcribe_with_whisper(audio_file, str(language) if language else None)

    if result:
        return ToolResult(
            content=f"📝 Transcription:\n{result.text}\n\nConfidence: {result.confidence:.0%}"
        )

    return ToolResult(
        content="Transcription failed. Ensure you have OpenAI API key configured for Whisper.",
        is_error=True,
    )


async def _transcribe_with_whisper(
    audio_path: str, language: str | None
) -> TranscriptionResult | None:
    """Transcribe using OpenAI Whisper API."""
    try:
        import openai

        client = openai.AsyncOpenAI()

        with open(audio_path, "rb") as audio_file:
            params = {"model": "whisper-1", "file": audio_file}
            if language:
                params["language"] = language

            response = await client.audio.transcriptions.create(**params)

        return TranscriptionResult(
            text=response.text,
            confidence=0.95,  # Whisper doesn't provide confidence scores
            language=language or "auto",
        )
    except Exception as e:
        logger.warning(f"Whisper transcription failed: {e}")
        return None


async def _transcribe_local(audio_path: str, language: str | None) -> TranscriptionResult | None:
    """Transcribe using local Whisper model."""
    try:
        import whisper

        model = whisper.load_model("base")

        result = model.transcribe(audio_path, language=language)

        return TranscriptionResult(
            text=result["text"],
            confidence=result.get("confidence", 0.8),
            language=result.get("language", language or "auto"),
        )
    except ImportError:
        logger.warning("Local Whisper not installed. Install: pip install openai-whisper")
        return None
    except Exception as e:
        logger.warning(f"Local transcription failed: {e}")
        return None


async def _speak_text(
    text: str,
    voice: object,
    speed: float,
    provider: str,
    context: ToolContext,
) -> ToolResult:
    """Convert text to speech."""
    global _voice_state

    async with _state_lock:
        if _voice_state["speaking"]:
            return ToolResult(
                content="Already speaking. Wait for current speech to finish.",
                is_error=True,
            )
        _voice_state["speaking"] = True

    try:
        if provider == "system":
            success = await _speak_with_system_tts(text, voice, speed)
        elif provider == "openai":
            success = await _speak_with_openai_tts(text, voice, speed)
        elif provider == "elevenlabs":
            success = await _speak_with_elevenlabs_tts(text, voice, speed)
        else:
            # Fallback to system
            success = await _speak_with_system_tts(text, voice, speed)

        if success:
            return ToolResult(content=f"🔊 Spoke: {text[:50]}...")
        else:
            return ToolResult(
                content=f"TTS failed for provider: {provider}. Try a different provider.",
                is_error=True,
            )

    finally:
        async with _state_lock:
            _voice_state["speaking"] = False


async def _speak_with_system_tts(text: str, voice: object, speed: float) -> bool:
    """Speak using system TTS (say on macOS, espeak on Linux)."""
    try:
        if sys.platform == "darwin":
            # macOS say command
            voice_arg = ["-v", str(voice)] if voice else []
            rate_arg = ["-r", str(int(200 * speed))]  # Default ~200 wpm

            result = await asyncio.create_subprocess_exec(
                "say",
                *voice_arg,
                *rate_arg,
                text,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
            )
            await result.wait()
            return result.returncode == 0

        elif sys.platform == "linux":
            # Try espeak or festival
            try:
                result = await asyncio.create_subprocess_exec(
                    "espeak",
                    "-s",
                    str(int(175 * speed)),
                    text,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.PIPE,
                )
                await result.wait()
                return result.returncode == 0
            except FileNotFoundError:
                result = await asyncio.create_subprocess_exec(
                    "festival",
                    "--tts",
                    stdin=subprocess.PIPE,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.PIPE,
                )
                result.stdin.write(text.encode())
                result.stdin.close()
                await result.wait()
                return result.returncode == 0

        elif sys.platform == "win32":
            # Windows TTS via PowerShell
            ps_cmd = f"Add-Type -AssemblyName System.Speech; "
            f"$synth = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
            f'$synth.Speak("{text.replace(chr(34), chr(34) + chr(34))}");'

            result = await asyncio.create_subprocess_exec(
                "powershell.exe",
                "-Command",
                ps_cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
            )
            await result.wait()
            return result.returncode == 0

        return False
    except Exception as e:
        logger.warning(f"System TTS failed: {e}")
        return False


async def _speak_with_openai_tts(text: str, voice: object, speed: float) -> bool:
    """Speak using OpenAI TTS API."""
    try:
        import openai

        client = openai.AsyncOpenAI()

        voices = ["alloy", "echo", "fable", "onyx", "nova", "shimmer"]
        selected_voice = str(voice) if voice in voices else "alloy"

        response = await client.audio.speech.create(
            model="tts-1",
            voice=selected_voice,  # type: ignore[arg-type]
            input=text,
            speed=speed,
        )

        # Save to temp file and play
        temp_path = os.path.join(tempfile.gettempdir(), f"io_tts_{int(time.time())}.mp3")
        response.stream_to_file(temp_path)

        # Play the audio
        return await _play_audio(temp_path)

    except Exception as e:
        logger.warning(f"OpenAI TTS failed: {e}")
        return False


async def _speak_with_elevenlabs_tts(text: str, voice: object, speed: float) -> bool:
    """Speak using ElevenLabs API."""
    try:
        import httpx

        api_key = os.environ.get("ELEVENLABS_API_KEY")
        if not api_key:
            logger.warning("ELEVENLABS_API_KEY not set")
            return False

        voice_id = str(voice) if voice else "21m00Tcm4TlvDq8ikWAM"  # Default voice

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

        async with httpx.AsyncClient() as client:
            response = await client.post(url, json=data, headers=headers)
            if response.status_code == 200:
                temp_path = os.path.join(tempfile.gettempdir(), f"io_tts_{int(time.time())}.mp3")
                with open(temp_path, "wb") as f:
                    f.write(response.content)
                return await _play_audio(temp_path)

        return False
    except Exception as e:
        logger.warning(f"ElevenLabs TTS failed: {e}")
        return False


async def _play_audio(audio_path: str) -> bool:
    """Play audio file."""
    try:
        if sys.platform == "darwin":
            result = await asyncio.create_subprocess_exec(
                "afplay", audio_path, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE
            )
        elif sys.platform == "linux":
            # Try multiple players
            for player in ["paplay", "aplay", "ffplay", "mpg123"]:
                try:
                    result = await asyncio.create_subprocess_exec(
                        player,
                        audio_path,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.PIPE,
                    )
                    await result.wait()
                    if result.returncode == 0:
                        return True
                except FileNotFoundError:
                    continue
            return False
        elif sys.platform == "win32":
            result = await asyncio.create_subprocess_exec(
                "powershell.exe",
                "-c",
                f'(New-Object Media.SoundPlayer "{audio_path}").PlaySync()',
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
            )
        else:
            return False

        await result.wait()
        return result.returncode == 0
    except Exception as e:
        logger.warning(f"Audio playback failed: {e}")
        return False


async def _get_voice_status(context: ToolContext) -> ToolResult:
    """Get voice system status."""
    global _voice_state

    async with _state_lock:
        status = {
            "enabled": _voice_state["voice_enabled"],
            "recording": _voice_state["recording"],
            "transcribing": _voice_state["transcribing"],
            "speaking": _voice_state["speaking"],
            "stt_provider": _voice_state["stt_provider"],
            "tts_provider": _voice_state["tts_provider"],
            "auto_tts": _voice_state["auto_tts"],
        }

    lines = [
        "🎙️ Voice System Status",
        "",
        f"Enabled: {'✓' if status['enabled'] else '✗'}",
        f"Recording: {'⏺️ Active' if status['recording'] else 'Idle'}",
        f"Speaking: {'🔊 Active' if status['speaking'] else 'Idle'}",
        "",
        "Configuration:",
        f"  STT Provider: {status['stt_provider']}",
        f"  TTS Provider: {status['tts_provider']}",
        f"  Auto-TTS: {'✓' if status['auto_tts'] else '✗'}",
        "",
        "Available Commands:",
        "  voice_record action=record duration=5",
        "  voice_transcribe",
        "  voice_speak text='Hello world'",
        "  voice_config enabled=true auto_tts=true",
    ]

    return ToolResult(content="\n".join(lines))


async def _configure_voice(arguments: dict[str, object], context: ToolContext) -> ToolResult:
    """Configure voice settings."""
    global _voice_state

    async with _state_lock:
        if "enabled" in arguments:
            _voice_state["voice_enabled"] = bool(arguments["enabled"])
        if "stt_provider" in arguments:
            _voice_state["stt_provider"] = str(arguments["stt_provider"])
        if "tts_provider" in arguments:
            _voice_state["tts_provider"] = str(arguments["tts_provider"])
        if "voice" in arguments:
            _voice_state["default_voice"] = str(arguments["voice"])
        if "auto_tts" in arguments:
            _voice_state["auto_tts"] = bool(arguments["auto_tts"])

        # Save to config
        config = load_config(context.home)
        voice_config = config.setdefault("voice", {})
        voice_config["enabled"] = _voice_state["voice_enabled"]
        voice_config["stt_provider"] = _voice_state["stt_provider"]
        voice_config["tts_provider"] = _voice_state["tts_provider"]
        voice_config["auto_tts"] = _voice_state["auto_tts"]

        from ..config import save_config

        save_config(config, context.home)

    return ToolResult(
        content="✓ Voice configuration updated.\nUse 'voice_status' to view settings."
    )


async def _list_voices(provider: object, context: ToolContext) -> ToolResult:
    """List available TTS voices."""
    if not provider:
        global _voice_state
        async with _state_lock:
            provider = _voice_state["tts_provider"]

    voices: dict[str, list[str]] = {
        "system": ["default", "Alex", "Samantha", "Victoria"]
        if sys.platform == "darwin"
        else ["default"],
        "openai": ["alloy", "echo", "fable", "onyx", "nova", "shimmer"],
        "elevenlabs": [
            "Rachel",
            "Domi",
            "Bella",
            "Antoni",
            "Elli",
            "Josh",
            "Arnold",
            "Adam",
            "Sam",
        ],
        "azure": ["en-US-JennyNeural", "en-US-GuyNeural", "en-GB-SoniaNeural"],
        "gcp": ["en-US-Standard-C", "en-US-Standard-D", "en-US-Wavenet-A"],
    }

    voice_list = voices.get(str(provider), ["default"])

    return ToolResult(
        content=f"Available voices for {provider}:\n" + "\n".join(f"  - {v}" for v in voice_list)
    )


# Register tools
GLOBAL_TOOL_REGISTRY.register(VoiceRecordTool())
GLOBAL_TOOL_REGISTRY.register(VoiceTranscribeTool())
GLOBAL_TOOL_REGISTRY.register(VoiceSpeakTool())
GLOBAL_TOOL_REGISTRY.register(VoiceStatusTool())
GLOBAL_TOOL_REGISTRY.register(VoiceConfigTool())
GLOBAL_TOOL_REGISTRY.register(VoiceListVoicesTool())
