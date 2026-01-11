import asyncio
import shutil
import struct
from contextlib import contextmanager
from enum import IntFlag
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

        with NamedTemporaryFile(suffix=".wav", delete=False) as tf:
            pass

        temp_wav = Path(tf.name)

        try:
            print("Copying...")
            shutil.copyfile(fname, temp_wav)

            size = temp_wav.stat().st_size
            if size < 8:
                print("File too small:", size)
                temp_wav.unlink()
                continue

            print("Fixing...")
            with temp_wav.open("r+b") as fp:
                fp.seek(4)
                print("Size:", temp_wav.stat().st_size - 8)
                fp.write(struct.pack("<I", temp_wav.stat().st_size - 8))

            print("Recognizing...")
            try:
                result = speech.recognize(temp_wav.name, language)
            except RuntimeError:
                print("Recognize nothing.")
                continue

        finally:
            temp_wav.unlink()

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
