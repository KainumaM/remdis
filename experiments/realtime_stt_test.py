import asyncio
import base64
import json
import pyaudio # sounddeviceの代わり
import websockets
import yaml
import numpy as np

# --- 設定項目 ---
# マイクのサンプリングレート（OpenAIの推奨は24000Hz）
MIC_SAMPLING_RATE = 48000
# 1度に処理する音声データのチャンクサイズ
CHUNK_SIZE = 8192
# PyAudio用のフォーマット
FORMAT = pyaudio.paInt16
MIC_CHANNELS = 2
# OpenAI Realtime APIのエンドポイント
OPENAI_WEBSOCKET_URL = "wss://api.openai.com/v1/realtime?intent=transcription"

# APIに送信する音声のフォーマット
API_SAMPLING_RATE = 24000
API_CHANNELS = 1

# 音声データを格納する非同期キュー
audio_queue = asyncio.Queue()

def load_api_key(config_path):
    with open(config_path, encoding='utf-8') as f:
        config = yaml.safe_load(f)
    return config['ChatGPT']['api_key']

async def microphone_stream():
    """マイクからの音声(2ch, 48kHz)を取得し、1ch, 24kHzに変換してキューに入れる"""
    p = pyaudio.PyAudio()
    stream = p.open(
        format=FORMAT,
        channels=MIC_CHANNELS,      # マイクのチャンネル数に設定
        rate=MIC_SAMPLING_RATE,    # マイクのサンプリングレートに設定
        input=True,
        frames_per_buffer=CHUNK_SIZE
    )
    print("マイクでの録音を開始しました。話しかけてください... (Ctrl+Cで終了)")

    while True:
        try:
            # マイクから音声データを読み込み
            data = await asyncio.get_event_loop().run_in_executor(
                None, stream.read, CHUNK_SIZE
            )
            
            # --- ここから音声変換処理 ---
            # 1. バイトデータをnumpy配列(16bit整数)に変換
            np_data = np.frombuffer(data, dtype=np.int16)
            
            # 2. 2チャンネルデータを(-1, 2)の形状に変換
            #    例: [L1, R1, L2, R2, ...] -> [[L1, R1], [L2, R2], ...]
            stereo_data = np_data.reshape(-1, MIC_CHANNELS)
            
            # 3. モノラルに変換 (左右のチャンネルを平均化)
            mono_data = stereo_data.mean(axis=1, dtype=np.int16)
            
            # 4. 24000Hzにダウンサンプリング (データを1つおきに取得)
            resampled_data = mono_data[::2]
            
            # 5. 再びバイトデータに戻す
            processed_data = resampled_data.tobytes()
            # --- 音声変換処理ここまで ---

             # ★デバッグポイント1: 変換後のデータがキューに入るか確認
            #print(f"DEBUG (mic): 変換後のデータ {len(processed_data)} バイトをキューに追加")
            # 変換後のデータをキューに入れる
            await audio_queue.put(processed_data)

        except asyncio.CancelledError:
            break

    print("マイクストリームを停止しています...")
    stream.stop_stream()
    stream.close()
    p.terminate()

async def openai_transcriber():
    """OpenAI Realtime APIに接続し、音声認識を行う"""
    
    # 変更箇所: 関数内でAPIキーを読み込み、ヘッダーを作成
    api_key = load_api_key('config/config.yaml')
    if not api_key:
        print("APIキーが読み込めませんでした。プログラムを終了します。")
        return
    
    # ユーザー提供のヘッダー形式を使用
    # 注意: 現在のAPIでは "OpenAI-Beta" ヘッダーは不要かもしれませんが、
    # 指定通りに含めています。
    headers = {
        "Authorization": f"Bearer {api_key}",
    }

    try:
        # 変更箇所: 作成したheadersをextra_headersに渡す
        async with websockets.connect(
            OPENAI_WEBSOCKET_URL,
            extra_headers=headers,
            ping_interval=5,
            ping_timeout=20
        ) as websocket:
            print("OpenAIに接続しました。")

            async def sender(ws):
                await ws.send(json.dumps({
                    "type": "session.update",
                    "session": {
                        "type": "transcription",
                        "audio": {
                            "input": {
                                "format": {
                                    "type": "audio/pcm",
                                    "rate": 24000,
                                },
                                "transcription": {
                                    #"delay": "medium",
                                    "language": "ja",
                                    "model": "gpt-4o-transcribe",
                                },
                                "turn_detection": {
                                    "type": "semantic_vad",
                                }                               
                            },
                        },
                    }
                }))
                while True:
                    try:
                        audio_chunk = await audio_queue.get()
                        # ★デバッグポイント2: キューからデータを取り出し、送信しているか確認
                        #print(f"DEBUG (sender): キューからデータを取得し、送信処理を実行")
                        encoded_data = base64.b64encode(audio_chunk).decode('utf-8')
                        json_payload = json.dumps({
                            "type": "input_audio_buffer.append",
                            "audio": encoded_data
                        })
                        await ws.send(json_payload)
                    except Exception as e:
                        print(f"送信エラー: {e}")
                        break

            async def receiver(ws):
                full_transcript = ""
                # ★デバッグポイント3: サーバーからの全メッセージを確認
                async for message in ws:
                    #print(f"DEBUG (receiver): サーバーからの生メッセージ -> {message}") # 生の応答をすべて表示
                    try:
                        response = json.loads(message)
                        # "text"キーに認識結果が含まれる
                        transcript = response.get("transcript", "")
                        
                        if transcript:
                           full_transcript += transcript
                           # 改行せずに同じ行に表示し続ける
                           print(f"\r認識中: {full_transcript}", end="", flush=True)

                    except Exception:
                        # JSON以外のメッセージやエラーは無視
                        pass
            print("音声認識を開始します。話しかけてください...")
            await asyncio.gather(sender(websocket), receiver(websocket))

    except websockets.exceptions.ConnectionClosedError as e:
        # 接続が閉じた際のエラー理由を詳しく表示
        print(f"\n接続が閉じられました: コード={e.code}, 理由='{e.reason}'")
    except Exception as e:
        print(f"\n予期せぬエラーが発生しました: {e}")

async def main():
    """メイン関数"""
    # 変更箇所: main関数でのAPIキーチェックは不要になったため削除
    mic_task = asyncio.create_task(microphone_stream())
    openai_task = asyncio.create_task(openai_transcriber())
    await asyncio.gather(mic_task, openai_task)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nプログラムを終了します。")