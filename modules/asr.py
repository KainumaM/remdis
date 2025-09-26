import sys, os
import time

import MeCab

import queue
import threading
import base64

import asyncio
import websockets
import json
from base import RemdisModule, RemdisUpdateType

STREAMING_LIMIT = 240  # 4 minutes

def get_text_increment(module, new_text, tagger):
    iu_buffer = []
    
    # 認識結果をトークンへ分割
    new_text = tagger.parse(new_text)
    tokens = new_text.strip().split(" ")

    # トークンがない場合は終了
    if tokens == [""]:
        return iu_buffer, []

    new_tokens = []
    iu_idx = 0
    token_idx = 0
    while token_idx < len(tokens):
        # 過去の音声認識結果と新しい音声認識結果を比較
        if iu_idx >= len(module.current_output):
            new_tokens.append(tokens[token_idx])
            token_idx += 1
        else:
            current_iu = module.current_output[iu_idx]
            iu_idx += 1
            if tokens[token_idx] == current_iu['body']:
                token_idx += 1
            else:
                # 変更があったIUをREVOKEに設定し格納
                current_iu['update_type'] = RemdisUpdateType.REVOKE
                iu_buffer.append(current_iu)

    # current_outputに新しい音声認識結果のIUを格納
    module.current_output = [iu for iu in module.current_output if iu['update_type'] is not RemdisUpdateType.REVOKE]

    return iu_buffer, new_tokens

class ASR(RemdisModule):
    def __init__(self,
                 pub_exchanges=['asr'],
                 sub_exchanges=['ain']):
        super().__init__(pub_exchanges=pub_exchanges,
                         sub_exchanges=sub_exchanges)

        self.buff_size = self.config['ASR']['buff_size']
        self.audio_buffer = queue.Queue() # 受信用キュー

        # 一つ前のステップの音声認識結果
        self.current_output = [] 

        # ASR用の変数
        self.language = self.config['ASR']['language']

        self.client = None
        self.streaming_config = None
        self.responses = []

        self.api_key = self.config['ChatGPT']['api_key']
        # 音声データを一時的に保持するためのスレッドセーフなキュー
        self.audio_buffer = queue.Queue()
        # 認識結果のテキストを非同期処理から同期処理へ渡すためのキュー
        self.transcript_queue = queue.Queue()
        
        self.tagger = MeCab.Tagger("-Owakati")

        self._is_running = True
        #self.resume_asr = False
        #無音を送る変更以下2行
        self.last_audio_time = time.time()
        self.silence_reported = False


    def run(self):
        # 音声データ受信スレッド
        t1 = threading.Thread(target=self.listen_loop)
        # 認識結果の処理・IU送信スレッド
        t2 = threading.Thread(target=self.produce_transcripts_loop)
        # 音声認識(非同期処理)スレッド
        t3 = threading.Thread(target=self.websocket_loop)

        # スレッド実行
        t1.start()
        t2.start()
        t3.start()

        return t1, t2, t3

    def listen_loop(self):
        self.subscribe('ain', self.callback)

    def produce_transcripts_loop(self):
        while self._is_running:                
            # 逐次音声認識結果の取得
            try:
                # iu_buffer: REVOKEしたIUを格納した送信用IUバッファ
                # new_tokens: 新しい音声認識結果のトークン系列
                current_text, is_completed = self.transcript_queue.get(timeout=1.0)
                iu_buffer, new_tokens = get_text_increment(self, current_text, self.tagger)
                if is_completed:
                    # is_completedがTRUEの時は空のIUをCOMMITで作成
                    output_iu = self.createIU_ASR('')
                    output_iu['update_type'] = RemdisUpdateType.COMMIT
                    # 送信バッファに格納
                    iu_buffer.append(output_iu)
                    #self.current_output = []
                else:
                    for token in new_tokens:
                        output_iu = self.createIU_ASR(token)
                        self.current_output.append(output_iu)
                        iu_buffer.append(output_iu)

                for snd_iu in iu_buffer:
                    self.printIU(snd_iu)
                    self.publish(snd_iu, 'asr')
            except queue.Empty:
                continue
            except Exception as e:
                sys.stderr.write(f"Error in transcript processing loop: {e}\n")

    def websocket_loop(self):
        try:
            asyncio.run(self.transcriber())
        except Exception as e:
            sys.stderr.write(f"Error in asyncio loop: {e}\n")
            self._is_running = False

    async def transcriber(self):
        # OpenAI Realtime APIのエンドポイント
        OPENAI_WEBSOCKET_URL = "wss://api.openai.com/v1/realtime?intent=transcription"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "OpenAI-Beta": "realtime=v1"
        }
        try:
            async with websockets.connect(
                OPENAI_WEBSOCKET_URL,
                extra_headers=headers,
                ping_interval=5,
                ping_timeout=20
            ) as websocket:
                sys.stderr.write("Successfully connected to OpenAI Realtime API.\n")
                sender_task = asyncio.create_task(self.sender(websocket))
                receiver_task = asyncio.create_task(self.receiver(websocket))
                await asyncio.gather(sender_task, receiver_task)
        except websockets.exceptions.ConnectionClosed as e:
            sys.stderr.write(f"Connection to OpenAI closed: {e.code} {e.reason}\n")
        except Exception as e:
            sys.stderr.write(f"An unexpected error occurred with OpenAI connection: {e}\n")
        finally:
            self._is_running = False

    async def sender(self, websocket):
        await websocket.send(json.dumps({
            "type": "transcription_session.update",
            "session": {
                "input_audio_format": "pcm16",
                "input_audio_transcription": {
                    "model": "gpt-4o-transcribe",
                    "language":  self.language
                },
            }
        }))
        loop = asyncio.get_event_loop()
        while self._is_running:
            try:
                audio_chunk = await loop.run_in_executor(None, self.audio_buffer.get, True, 1.0)
                if audio_chunk:
                    # 無音を送る変更以下2行
                    self.last_audio_time = time.time()
                    self.silence_reported = False
                    encoded_data = base64.b64encode(audio_chunk).decode('utf-8')
                    await websocket.send(json.dumps({
                        "type": "input_audio_buffer.append",
                        "audio": encoded_data
                    }))
            except queue.Empty:
                # 無音を送る変更if文のブロックすべて: 音声がなければ沈黙時間をチェック ---
                if time.time() - self.last_audio_time > 1.0 and not self.silence_reported:
                    sys.stderr.write(f"Silence detected for over 1.0 seconds. Reporting COMMIT.\n")
                    # COMMITを発行するための特別なメッセージをキューに入れる
                    self.transcript_queue.put(("", True))
                    # 報告済みフラグを立てる
                    self.silence_reported = True

                continue
            except Exception as e:
                sys.stderr.write(f"Error in sender: {e}\n")
                break
    
    async def receiver(self, websocket):
        current_full_transcript = ""
        async for message in websocket:
            try:
                response = json.loads(message)
                msg_type = response.get("type")

                # --- 変更: メッセージのtypeに応じて処理を分岐 ---
                if msg_type == "conversation.item.input_audio_transcription.delta":
                    delta = response.get("delta", "")
                    if delta:
                        current_full_transcript += delta
                        # 中間結果として、結合した全文をキューに入れる
                        self.transcript_queue.put((current_full_transcript, False))

                elif msg_type == "conversation.item.input_audio_transcription.completed":
                    final_transcript = response.get("transcript", "")
                    if final_transcript:
                        # completedのテキストを正として更新
                        current_full_transcript = final_transcript
                        # 中間結果として、最終的な全文をキューに入れる
                        self.transcript_queue.put((current_full_transcript, False))

                elif msg_type in ["input_audio_buffer.speech_stopped", "input_audio_buffer.committed"]:
                    # これまでにテキストがあればCOMMIT信号を送る
                    if current_full_transcript:
                        # COMMITを発行するための特別なメッセージをキューに入れる
                        self.transcript_queue.put(("", True))
                        # 次の発話のためにリセット
                        current_full_transcript = ""

            except Exception as e:
                sys.stderr.write(f"Error processing received message: {e}\n")

    def createIU_ASR(self, token):
        iu = self.createIU(token, 'asr', RemdisUpdateType.ADD)
        return iu
    
    # メッセージ受信用コールバック関数
    def callback(self, ch, method, properties, in_msg):
        in_msg = self.parse_msg(in_msg)
        self.audio_buffer.put(base64.b64decode(in_msg['body'].encode()))

    def stop(self):
        """Signals all running threads to stop."""
        sys.stderr.write("Sending stop signal to all threads...\n")
        self._is_running = False

def main():
    asr = ASR()
    t1, t2, t3 = asr.run()
    
    try:
        while asr._is_running:
            time.sleep(1)
    except KeyboardInterrupt:
        sys.stderr.write("KeyboardInterrupt received. Shutting down gracefully...\n")
    finally:
        asr.stop()
        t1.join()
        t2.join()
        t3.join()
        sys.stderr.write("All threads have been joined. Exiting.\n")

if __name__ == '__main__':
    main()
