import tempfile
import time
from contextlib import contextmanager
from enum import IntFlag

import dialogs
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


def main() -> None:

    language = "ja_JP"
    with AVAudioSession() as audio_session:
        with tempfile.NamedTemporaryFile(suffix=".m4a") as tf:
            recorder = sound.Recorder(tf.name)

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

            if not audio_session.setCategory_withOptions_error_(
                audio_session.category(),
                AVAudioSessionCategoryOptions.DefaultToSpeaker,
                None,
            ):
                raise RuntimeError(
                    "Failed to set audio session category with options"
                )

            dialogs.alert(
                "Recording...", "", "Finish", hide_cancel_button=True
            )
            recorder.stop()
            result = speech.recognize(tf.name, language)

        print("=== Details ===")
        print(result)
        print("=== Transcription ===")
        print(result[0][0])
        speech.say(result[0][0], language)

        while speech.is_speaking():
            time.sleep(0.1)


if __name__ == "__main__":
    main()
