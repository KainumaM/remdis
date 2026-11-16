import sys
import time
import re
import os
import threading
import queue
import yaml
import json

# LLMライブラリは別途インストールが必要です: pip install openai
try:
    import openai
except ImportError:
    print(f"[INFO] error: 'openai'ライブラリが見つかりません。'pip install openai'を実行してください。")
    sys.exit(1)

def load_prompt(prompt_name):
    PROMPT_DIR = "LLM_prompts"
    file_path = os.path.join(PROMPT_DIR, f"{prompt_name}.txt")

    if not os.path.exists(file_path):
        print(f"[INFO] warning: プロンプトファイル '{file_path}' が見つかりません。")
        return None
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            prompt_content = f.read()
        print(f"[INFO] プロンプト '{file_path}' を正常に読み込みました。")
        return prompt_content
    except Exception as e:
        print(f"[INFO] error: プロンプトファイル読み込み中に問題が発生しました: {e}")
        return None

def load_config(config_filename):
    if not os.path.exists(config_filename):
        print(f"[INFO] warning: 設定ファイル '{config_filename}' が見つかりません。デフォルト設定を使用します。")
        # ファイルがない場合は、最低限のダミー設定を返す
        return {'ChatGPT': {'max_tokens': 512}}

    try:
        with open(config_filename, encoding='utf-8') as f:
            config = yaml.safe_load(f)
        return config
    except Exception as e:
        print(f"[INFO] error: 設定ファイル読み込み中に問題が発生しました: {e}。デフォルト設定を使用します。")
        return {'ChatGPT': {'max_tokens': 512}}


class ResponseGenerator:
    def __init__(self, config, dialogue_history, query):
        
        self.response_fragment = ''
        
        print("\n" + "="*60)
        print("[DEBUG] LLM Request Payload (Sending ALWAYS complete history):")
        print(json.dumps(dialogue_history, indent=2, ensure_ascii=False))
        print("="*60 + "\n")

        # LLMサーバー設定（元のコードの設定値を維持）
        llm_url = 'http://192.168.1.160:8000/v1'
        model_name = 'Qwen/Qwen2.5-14B-Instruct-GPTQ-Int8'
        max_tokens = config.get('ChatGPT', {}).get('max_tokens', 512)

        try:
            self.client = openai.OpenAI(
                base_url = llm_url,
                api_key = 'dummy',
                timeout = 20.0
            )
        except Exception as e:
             print(f"[INFO] error: OpenAIクライアントの初期化に失敗しました: {e}")
             raise

        try:
            # ストリーミングリクエストの開始
            self.stream = self.client.chat.completions.create(
                model = model_name,
                messages = dialogue_history,
                stream=True,
                max_tokens=max_tokens,
                temperature=0.8
            )
        except openai.APIError as e:
             print(f"[INFO] error: LLM API呼び出しに失敗しました: {e}")
             raise
    
    # 応答の断片を順次返す (パースは行わず、トークンが来たら即座に出力)
    def __next__(self):
        for chunk in self.stream:
            raw_chunk_str = chunk.model_dump_json()
            #print(f"\n[DEBUG] {raw_chunk_str}")
            new_token = chunk.choices[0].delta.content
            if new_token:
                # 応答全体をバッファリングするのではなく、トークンをそのまま返す
                self.response_fragment += new_token
                return {"raw_token": new_token}

        raise StopIteration
    
    def __iter__(self):
        return self


# --- ResponseChatGPT クラス (対話履歴管理とLLM呼び出し) ---

class ResponseChatGPT():
    def __init__(self, config, system_prompt):
        self.config = config
        self.system_prompt = system_prompt

        # システムプロンプトがNoneの場合は履歴に追加しない
        self.dialogue_history = [{"role": "system", "content": self.system_prompt},
                                 #{"role": "user", "content": "こんにちは。"},
                                 #{"role": "assistant", "content": "おはようございます、よろしくお願いします。<0_平静,2_うなずく>"},
                                 #{"role": "user", "content": "お願いします"},
                                 #{"role": "assistant", "content": "まずはお話ししましょう。今日はどうですか？<0_平静,2_うなずく>"},
        ]

        self.user_utterance = ''
        self.response = None
    
    def run(self, asr_timestamp, user_utterance, last_asr_iu_id, parent_llm_buffer):
        self.user_utterance = user_utterance

        if user_utterance:
            # ユーザ発言を対話履歴に追加
            self.dialogue_history.append({"role": "user", "content": user_utterance})
        
        try:
            # ResponseGeneratorを対話履歴で初期化
            self.response = ResponseGenerator(self.config, self.dialogue_history, user_utterance)
            parent_llm_buffer.put(self)
        except Exception as e:
            print(f"[INFO] error: LLM実行に失敗しました: {e}")

if __name__ == "__main__":
    
    # ファイル存在チェックと、存在しない場合のコンソール出力
    config = load_config('config/config.yaml')
    system_prompt = load_prompt('okada') 

    # 初期化
    openai.api_key = 'dummy' 
    user_query = 'こんにちは'
    llm_buffer = queue.Queue()
    llm_handler = ResponseChatGPT(config, system_prompt)
    
    print(f"[INFO] === LLM実行開始: 入力 '{user_query}' ===")

    # スレッドを立ててLLM呼び出しを実行
    t = threading.Thread(
        target=llm_handler.run,
        args=(time.time(),
              user_query,
              None,
              llm_buffer)
    )
    t.start()

    try:
        # LLMからの応答オブジェクトをバッファから取得
        llm_instance = llm_buffer.get(timeout=5) # 応答を待つ
    except queue.Empty:
        print("[ERROR] LLM実行スレッドから応答オブジェクトを取得できませんでした (タイムアウト)。")
        t.join()
        sys.exit(1)

    full_response = ""
    print("\n--- 応答ストリーム---")
    
    # ResponseGenerator (イテレータ) から生のトークンを順次取得
    for part in llm_instance.response:
        if "raw_token" in part:
            raw_token = part["raw_token"]
            
            # 生のトークンをそのままコンソールに出力
            print(raw_token, end="", flush=True)
            full_response += raw_token

    
    # スレッドが終了するのを待つ
    t.join()
    print("\n---------------")
    print(f"\n最終的なLLM応答: {full_response}")
