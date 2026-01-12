import asyncio
import wave
from chunk import Chunk
from collections.abc import MutableSequence
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass, field
from enum import IntFlag
from functools import partial
from os import unlink
from os.path import getsize
from pprint import pprint
from tempfile import NamedTemporaryFile
from typing import cast
from unittest.mock import patch

import motion
import numpy as np
import sound
import speech
from objc_util import ObjCClass

AVAudioSession = ObjCClass("AVAudioSession")


class AVAudioSessionCategoryOptions(IntFlag):
    MixWithOthers = 0x1
    DuckOthers = 0x2
    AllowBluetooth = 0x4
    DefaultToSpeaker = 0x8
    InterruptSpokenAudioAndMixWithOthers = 0x11
    AllowBluetoothA2DP = 0x20
    AllowAirPlay = 0x40
    OverrideMutedMicrophoneInterruption = 0x80


class Recorder:
    def __init__(self, file_path: str):
        self._recorder = sound.Recorder(file_path)
        self._restore_audio_session = lambda: True  # Do nothing by default

    def record(self):
        audio_session = AVAudioSession.sharedInstance()
        self._restore_audio_session = partial(
            audio_session.setCategory_mode_options_error_,
            audio_session.category(),
            audio_session.mode(),
            audio_session.categoryOptions(),
            None,
        )

        # The `.record()` method changes AVAudioSession as follows:
        # [AVAudioSessionCategory]
        #   from AVAudioSessionCategoryPlayback
        #   to   AVAudioSessionCategoryPlayAndRecord
        # [AVAudioSessionMode]
        #   from AVAudioSessionModeDefault
        #   to   AVAudioSessionModeDefault
        # [AVAudioSessionCategoryOptions]
        #   from 1
        #   to   0
        r = self._recorder.record()

        if not audio_session.setCategory_withOptions_error_(
            audio_session.category(),
            AVAudioSessionCategoryOptions.DefaultToSpeaker
            | AVAudioSessionCategoryOptions.AllowBluetooth,
            None,
        ):
            raise RuntimeError("Failed to adjust audio session")

        return r

    def stop(self):
        r = self._recorder.stop()

        if not self._restore_audio_session():
            raise RuntimeError("Failed to restore audio session")

        return r


class ResilientWaveFile(wave.Wave_read):
    @property
    def __riff_chunk(self) -> Chunk:
        return cast(Chunk, self._file)  # type: ignore[attr-defined]

    @property
    def __data_chunk(self) -> Chunk:
        return cast(Chunk, self._data_chunk)  # type: ignore[attr-defined]

    def getfilesize(self) -> int:
        return getsize(self.__riff_chunk.file.name)

    @contextmanager
    def _override_riff_chunk_size(self):
        size = self.getfilesize() - self.__riff_chunk.offset
        with patch.object(self.__riff_chunk, "chunksize", new=size):
            yield

    @contextmanager
    def _override_data_chunk_size(self):
        size = self.getfilesize() - self.__data_chunk.offset
        with patch.object(self.__data_chunk, "chunksize", new=size):
            yield

    def is_fragmented(self) -> bool:
        riff_chunk = self.__riff_chunk
        return riff_chunk.offset + riff_chunk.getsize() != self.getfilesize()

    def initfp(self, file):
        super().initfp(file)

        if self.is_fragmented():
            frame_size = self.getnchannels() * self.getsampwidth()
            with self._override_data_chunk_size():
                self._nframes = self.__data_chunk.getsize() // frame_size

    def readframes(self, nframes: int) -> bytes:
        stack = ExitStack()

        if self.is_fragmented():
            stack.enter_context(self._override_riff_chunk_size())
            stack.enter_context(self._override_data_chunk_size())

        with stack:
            return super().readframes(nframes)


@dataclass(frozen=True)
class Segment:
    timestamp: float
    confidence: float
    substring: str
    duration: float
    alternative_substrings: list[str] = field(default_factory=list)


class Transcriber:
    def __init__(self, file_path: str):
        self.file_path = file_path

    @staticmethod
    def _recognize(
        file_path, language: str
    ) -> tuple[str, MutableSequence[Segment]]:

        string, segments = speech.recognize(file_path, language)[0]
        return string, [Segment(**segment) for segment in segments]

    def transcribe(
        self, language: str, offset: float = 0.0
    ) -> tuple[str, MutableSequence[Segment]]:

        with ResilientWaveFile(self.file_path) as wav_in:

            if offset == 0 and not wav_in.is_fragmented():
                return self._recognize(self.file_path, language)

            with NamedTemporaryFile(suffix=".wav", delete=False) as tf:
                pass

            try:
                with wave.open(tf.name, "wb") as wav_out:
                    wav_out.setnchannels(wav_in.getnchannels())
                    wav_out.setsampwidth(wav_in.getsampwidth())
                    wav_out.setframerate(wav_in.getframerate())

                    wav_out.writeframes(wav_in.readframes(wav_in.getnframes()))

                return self._recognize(tf.name, language)
            finally:
                unlink(tf.name)


async def speak_aloud(queue: asyncio.Queue[str], language: str):
    while True:
        text = await queue.get()
        print(f"Saying: {text}")
        speech.say(text, language)

        while speech.is_speaking():
            await asyncio.sleep(0.1)

        queue.task_done()


async def extract_phrases(
    queue: asyncio.Queue[str], fname: str, language: str
):
    said: list[Segment] = []
    transcriber = Transcriber(fname)
    while True:
        await asyncio.sleep(1)

        try:
            offset = said[-1].timestamp + said[-1].duration
        except IndexError:
            offset = 0.0

        try:
            string, segments = transcriber.transcribe(language, offset)
        except (EOFError, wave.Error, RuntimeError):
            continue
        except Exception as e:
            print("Unexpected error:", e)
            continue

        segments = segments[len(said) :]
        pprint(segments)

        while segments and segments[-1].confidence < 0.5:
            segments.pop()

        say = "".join(segment.substring for segment in segments)

        await queue.put(say)
        said.extend(segments)
        print(f"Said up to {len(said)} segments")


async def record_audio(fname: str):
    recorder = Recorder(fname)
    recorder.record()

    motion.start_updates()

    try:
        while np.linalg.norm(np.array(motion.get_user_acceleration())) < 1:
            await asyncio.sleep(0.1)
    finally:
        motion.stop_updates()
        recorder.stop()


async def main():
    with NamedTemporaryFile(suffix=".wav") as tf:
        queue = asyncio.Queue[str]()
        extractor = asyncio.create_task(
            extract_phrases(queue, tf.name, "ja_JP")
        )
        speaker = asyncio.create_task(speak_aloud(queue, "ja_JP"))

        await record_audio(tf.name)
        await asyncio.sleep(1)

        extractor.cancel()
        await queue.join()
        speaker.cancel()


if __name__ == "__main__":
    asyncio.run(main())
