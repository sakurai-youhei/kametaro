import asyncio
from contextlib import contextmanager
from enum import IntFlag
from pprint import pprint
from tempfile import NamedTemporaryFile

import console
import sound
import speech
from objc_util import ObjCClass


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
def AVAudioSession():
    AVAudioSession = ObjCClass("AVAudioSession")
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
            result = speech.recognize(fname, language)
        except RuntimeError:
            continue

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

    AVAudioSession = ObjCClass("AVAudioSession")
    audio_session = AVAudioSession.sharedInstance()

    if not audio_session.setCategory_withOptions_error_(
        audio_session.category(),
        AVAudioSessionCategoryOptions.DefaultToSpeaker,
        None,
    ):
        raise RuntimeError("Failed to configure audio session")

    await asyncio.to_thread(
        console.alert, "Recording...", hide_cancel_button=True
    )
    recorder.stop()


async def main():
    with AVAudioSession():
        with NamedTemporaryFile(suffix=".m4a") as tf:
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
