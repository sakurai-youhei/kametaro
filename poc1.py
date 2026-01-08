import tempfile
import time

import dialogs
import objc_util
import sound
import speech


def main() -> None:
    # print("setting silent switch to false")
    # sound.set_honors_silent_switch(False)
    speech.say("Hello from poc1.py!")

    AVAudioSession = objc_util.ObjCClass("AVAudioSession")
    audio_session = AVAudioSession.sharedInstance()

    # AVAudioSessionCategory: AVAudioSessionCategoryPlayback
    # AVAudioSessionMode: AVAudioSessionModeDefault
    # AVAudioSessionCategoryOptions: 1
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

        # AVAudioSessionCategory: AVAudioSessionCategoryPlayback
        # AVAudioSessionMode: AVAudioSessionModeDefault
        # AVAudioSessionCategoryOptions: 1
        print("\n=== 録音開始前のオーディオセッション状態 ===")
        print(f"Category: {audio_session.category()}")
        print(f"Mode: {audio_session.mode()}")
        print(f"Options: {audio_session.categoryOptions()}")

        recorder.record()
        print("\n=== オーディオモードとオプションを変更中 ===")
        if not audio_session.setCategory_mode_options_error_(
            audio_session.category(),
            "AVAudioSessionModeVoiceChat",
            original_options,
            None,
        ):
            print("オーディオモードとオプションの復元に失敗")

        # AVAudioSessionCategory: AVAudioSessionCategoryPlayAndRecord
        # AVAudioSessionMode: AVAudioSessionModeDefault
        # AVAudioSessionCategoryOptions: 0
        print("\n=== 録音中のオーディオセッション状態 ===")
        print(f"Category: {audio_session.category()}")
        print(f"Mode: {audio_session.mode()}")
        print(f"Options: {audio_session.categoryOptions()}")

        dialogs.alert("Recording...", "", "Finish", hide_cancel_button=True)
        recorder.stop()

        del recorder
        print("\n=== recorder削除後のオーディオセッション状態 ===")
        print(f"Category: {audio_session.category()}")
        print(f"Mode: {audio_session.mode()}")
        print(f"Options: {audio_session.categoryOptions()}")

        result = speech.recognize(tf.name, language)

    # AVAudioSessionCategory: AVAudioSessionCategoryPlayback
    # AVAudioSessionMode: AVAudioSessionModeDefault
    # AVAudioSessionCategoryOptions: 1
    # print("\n=== オーディオセッションを復元中 ===")
    # if not audio_session.setCategory_mode_options_error_(
    #    original_category, original_mode, original_options, None
    # ):
    #    print("オーディオセッションの復元に失敗")

    print("=== Details ===")
    print(result)
    print("=== Transcription ===")
    print(result[0][0])
    speech.say(result[0][0], language)

    while speech.is_speaking():
        time.sleep(0.1)


if __name__ == "__main__":
    main()
