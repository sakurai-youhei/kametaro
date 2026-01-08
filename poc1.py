import tempfile
import time

import dialogs
import sound
import speech


def main() -> None:
    speech.say("Hello from poc1.py!")

    language = "ja_JP"
    with tempfile.NamedTemporaryFile(suffix=".m4a") as tf:
        recorder = sound.Recorder(tf.name)
        recorder.record()
        dialogs.alert("Recording...", "", "Finish", hide_cancel_button=True)
        recorder.stop()

        result = speech.recognize(tf.name, language=language)

    print("=== Details ===")
    print(result)
    print("=== Transcription ===")
    print(result[0][0])
    speech.say(result[0][0], language=language)

    while speech.is_speaking():
        time.sleep(0.1)


if __name__ == "__main__":
    main()
