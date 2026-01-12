import asyncio
import shutil
import struct
import wave
from chunk import Chunk
from contextlib import contextmanager
from enum import IntFlag
from os import SEEK_CUR
from pathlib import Path
from pprint import pprint
from tempfile import NamedTemporaryFile

import motion
import numpy as np
import sound
import speech
from objc_util import ObjCClass

AVAudioSession = ObjCClass("AVAudioSession")
AVAudioRecorder = ObjCClass("AVAudioRecorder")


class AVAudioSessionCategoryOptions(IntFlag):
    MixWithOthers = 0x1
    DuckOthers = 0x2
    AllowBluetooth = 0x4
    DefaultToSpeaker = 0x8
    InterruptSpokenAudioAndMixWithOthers = 0x11
    AllowBluetoothA2DP = 0x20
    AllowAirPlay = 0x40
    OverrideMutedMicrophoneInterruption = 0x80


@contextmanager
def audio_session():
    audio_session = AVAudioSession.sharedInstance()

    original = (
        audio_session.category(),
        audio_session.mode(),
        audio_session.categoryOptions(),
    )

    try:
        yield audio_session
    finally:
        if not audio_session.setCategory_mode_options_error_(*original, None):
            raise RuntimeError("Failed to restore audio session")


async def speak_aloud(queue: asyncio.Queue[str], language: str):
    while True:
        text = await queue.get()
        speech.say(text, language)

        while speech.is_speaking():
            await asyncio.sleep(0.1)

        queue.task_done()


async def extract_phrases(
    queue: asyncio.Queue[str], fname: str, language: str
):
    read = 0
    while True:
        await asyncio.sleep(1)

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

                data_chunk_size = file_size - fp.tell()
                data_chunk_size //= frame_width
                data_chunk_size *= frame_width
                print(f"Correcting data chunk size to {data_chunk_size} bytes")

                fp.seek(-4, SEEK_CUR)
                fp.write(struct.pack("<I", data_chunk_size))

            try:
                print("Recognizing...")
                result = speech.recognize(temp_wav.absolute(), language)
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


async def record_audio(fname: str):
    recorder = sound.Recorder(fname)

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
    recorder.record()

    audio_session = AVAudioSession.sharedInstance()
    if not audio_session.setCategory_withOptions_error_(
        audio_session.category(),
        AVAudioSessionCategoryOptions.DefaultToSpeaker,
        None,
    ):
        raise RuntimeError("Failed to configure audio session")

    motion.start_updates()

    try:
        while np.linalg.norm(np.array(motion.get_user_acceleration())) < 1:
            await asyncio.sleep(0.1)
    finally:
        motion.stop_updates()
        recorder.stop()


async def main():
    with audio_session(), NamedTemporaryFile(suffix=".wav") as tf:
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
