import asyncio
import wave
from chunk import Chunk
from contextlib import ExitStack, contextmanager
from enum import IntFlag
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


class Recorder(sound.Recorder):
    def record(self):
        audio_session = AVAudioSession.sharedInstance()
        self.__original = (
            audio_session.category(),
            audio_session.mode(),
            audio_session.categoryOptions(),
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
        r = super().record()

        if not audio_session.setCategory_withOptions_error_(
            audio_session.category(),
            AVAudioSessionCategoryOptions.DefaultToSpeaker
            | AVAudioSessionCategoryOptions.AllowBluetooth,
            None,
        ):
            raise RuntimeError("Failed to adjust audio session")

        return r

    def stop(self):
        r = super().stop()

        audio_session = AVAudioSession.sharedInstance()
        if not audio_session.setCategory_mode_options_error_(
            *self.__original, None
        ):
            raise RuntimeError("Failed to restore audio session")

        return r


class InterimWaveFile(wave.Wave_read):
    @property
    def __riff_chunk(self) -> Chunk:
        return cast(Chunk, self._file)  # type: ignore[attr-defined]

    @property
    def __data_chunk(self) -> Chunk:
        return cast(Chunk, self._data_chunk)  # type: ignore[attr-defined]

    @property
    def __file_size(self) -> int:
        return getsize(self.__riff_chunk.file.name)

    @contextmanager
    def __override_riff_chunk_size(self):
        size = self.__file_size - self.__riff_chunk.offset
        with patch.object(self.__riff_chunk, "chunksize", new=size):
            yield

    @contextmanager
    def __override_data_chunk_size(self):
        size = self.__file_size - self.__data_chunk.offset
        with patch.object(self.__data_chunk, "chunksize", new=size):
            yield

    def is_finalized(self) -> bool:
        riff_chunk = self.__riff_chunk
        return riff_chunk.offset + riff_chunk.getsize() == self.__file_size

    def initfp(self, file):
        super().initfp(file)

        if not self.is_finalized():
            frame_size = self.getnchannels() * self.getsampwidth()
            with self.__override_data_chunk_size():
                self._nframes = self.__data_chunk.getsize() // frame_size

    def readframes(self, nframes: int) -> bytes:
        stack = ExitStack()

        if not self.is_finalized():
            stack.enter_context(self.__override_riff_chunk_size())
            stack.enter_context(self.__override_data_chunk_size())

        with stack:
            return super().readframes(nframes)


class Transcriber:
    def __init__(self, file_path: str):
        self.file_path = file_path

    def transcribe(self, language: str):
        with InterimWaveFile(self.file_path) as wavin:

            if wavin.is_finalized():
                return speech.recognize(self.file_path, language)

            with NamedTemporaryFile(suffix=".wav", delete=False) as tf:
                pass

            try:
                with wave.open(tf.name, "wb") as wavout:
                    wavout.setnchannels(wavin.getnchannels())
                    wavout.setsampwidth(wavin.getsampwidth())
                    wavout.setframerate(wavin.getframerate())

                    wavout.writeframes(wavin.readframes(wavin.getnframes()))
                return speech.recognize(tf.name, language)
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
    read = 0
    transcriber = Transcriber(fname)
    while True:
        await asyncio.sleep(1)

        try:
            result = transcriber.transcribe(language)
        except (EOFError, wave.Error, RuntimeError) as e:
            print(e)
            continue
        except Exception as e:
            print("Unexpected error:", e)
            continue

        pprint(result)

        await queue.put(result[0][0][read:])
        read = len(result[0][0])
        print(f"Read up to {read} characters")

        """
        try:
            n_channels, sample_width, *_ = wave.open(fname).getparams()
        except (EOFError, wave.Error):
            continue

        frame_width = n_channels * sample_width

        with NamedTemporaryFile(suffix=".wav", delete=False) as tf:
            pass

        temp_wav = Path(tf.name)

        try:
            shutil.copyfile(fname, temp_wav)
            file_size = temp_wav.stat().st_size

            print(f"Copied {file_size} bytes")

            with temp_wav.open("r+b") as fp:
                riff_chunk_size = file_size - 8
                print(f"Correcting RIFF chunk size to {riff_chunk_size} bytes")

                fp.seek(4)
                fp.write(struct.pack("<I", riff_chunk_size))
                assert fp.read(4) == b"WAVE"

                chunk = Chunk(fp, bigendian=False)
                while chunk.getname() != b"data":
                    print(f"Skipping chunk {chunk.getname().decode()}")
                    chunk.skip()
                    chunk = Chunk(fp, bigendian=False)

                data_chunk_size = file_size - fp.tell()
                data_chunk_size //= frame_width
                data_chunk_size *= frame_width
                print(f"Correcting data chunk size to {data_chunk_size} bytes")

                fp.seek(-4, SEEK_CUR)
                fp.write(struct.pack("<I", data_chunk_size))

            try:
                print("Recognizing...")
                result = speech.recognize(str(temp_wav), language)
            except RuntimeError as e:
                print("Recognized nothing", e)
                continue

        except Exception as e:
            print(e)
        finally:
            temp_wav.unlink(missing_ok=True)

        pprint(result)

        await queue.put(result[0][0][read:])
        read = len(result[0][0])
        """


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
