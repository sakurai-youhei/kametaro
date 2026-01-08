import tempfile
import time

import dialogs
import objc_util
import sound
import speech


def main() -> None:
    print("setting silent switch to false")
    sound.set_honors_silent_switch(False)
    speech.say("Hello from poc1.py!")

    AVAudioSession = objc_util.ObjCClass("AVAudioSession")
    audio_session = AVAudioSession.sharedInstance()

    # 録音前のオーディオセッション状態を保存
    print("=== 録音前のオーディオセッション状態 ===")
    original_category = audio_session.category()
    original_mode = audio_session.mode()
    original_options = audio_session.categoryOptions()
    print(f"Category: {original_category}")
    print(f"Mode: {original_mode}")
    print(f"Options: {original_options}")

    language = "ja_JP"
    with tempfile.NamedTemporaryFile(suffix=".m4a") as tf:
        recorder = sound.Recorder(tf.name)
        print("\n=== 録音開始前のオーディオセッション状態 ===")
        print(f"Category: {audio_session.category()}")
        print(f"Mode: {audio_session.mode()}")
        print(f"Options: {audio_session.categoryOptions()}")

        recorder.record()

        # 録音中のオーディオセッション状態を確認
        print("\n=== 録音中のオーディオセッション状態 ===")
        print(f"Category: {audio_session.category()}")
        print(f"Mode: {audio_session.mode()}")
        print(f"Options: {audio_session.categoryOptions()}")

        dialogs.alert("Recording...", "", "Finish", hide_cancel_button=True)
        recorder.stop()

        result = speech.recognize(tf.name, language)

    # オーディオセッションを元の状態に復元
    print("\n=== オーディオセッションを復元中 ===")
    success = audio_session.setCategory_mode_options_error_(
        original_category, original_mode, original_options, None
    )
    if success:
        print("オーディオセッションの復元に成功")
        print(f"復元後 Category: {audio_session.category()}")
        print(f"復元後 Mode: {audio_session.mode()}")
        print(f"復元後 Options: {audio_session.categoryOptions()}")
    else:
        print("オーディオセッションの復元に失敗")

    print("=== Details ===")
    print(result)
    print("=== Transcription ===")
    print(result[0][0])
    speech.say(result[0][0], language)

    while speech.is_speaking():
        time.sleep(0.1)


if __name__ == "__main__":
    main()
