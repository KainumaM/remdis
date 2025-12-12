import sys
import json
import time
import re
import string
import os

import openai

from base import MMDAgentEXLabel
from logger import logger

def load_prompt(prompt_name):
    #指定された名前のプロンプトファイルを読み込む
    PROMPT_DIR = "../LLM_prompts"  # プロンプトが格納されているディレクトリ
    file_path = os.path.join(PROMPT_DIR, f"{prompt_name}.txt")

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            prompt_content = f.read()
        logger.info(f"プロンプト '{file_path}' を正常に読み込みました。")
        return prompt_content
    except FileNotFoundError:
        logger.info(f"error: プロンプトファイル '{file_path}' が見つかりません。")
        return None
    except Exception as e:
        logger.info(f"error: プロンプトファイル読み込み中に問題が発生しました: {e}")
        return None

class ResponseGenerator:
    def __init__(self, config, dialogue_history, query):
        # 設定の読み込み

        # 生成中の応答を保持・パースする変数
        self.response_fragment = ''
        self.punctuation_pattern = re.compile('[、。！？\n]')
    
        self.in_metadata = False

        logger.info(f'Call ChatGPT: {query=}')
        llm_url = 'http://192.168.1.161:8000/v1'
        model_name = 'meta-llama/Llama-3.1-8B-Instruct'

        # クライアントの初期化
        self.client = openai.OpenAI(
            base_url = llm_url,
            api_key = 'dummy',
        )

        # ストリーミングリクエストの開始
        self.stream = self.client.chat.completions.create(
            model = model_name,
            messages = dialogue_history,
            stream=True,
            max_tokens=config['ChatGPT']['max_tokens']
        )
    
    # Dialogueのsend_response関数で呼び出され，応答の断片を順次返す
    def __next__(self):
        # 引数（例: '1_喜び,6_会釈'）をパースして，expressionとactionを取得
        def _parse_split(split):
            expression = MMDAgentEXLabel.id2expression[0]
            action = MMDAgentEXLabel.id2action[0]

            # expression/actionを取得
            if "," in split:
                expression, action = split.split(",", 1)

                expression = expression.split("_")[0]
                expression = int(expression) if expression.isdigit() else 0
                expression = MMDAgentEXLabel.id2expression[expression]

                action = action.split("_")[0]
                action = int(action) if action.isdigit() else 0
                action = MMDAgentEXLabel.id2action[action]

            return {
                "expression": expression,
                "action": action
            }
  
        # ChatGPTの応答を順次パースして返す
        for chunk in self.stream:
            new_token = chunk.choices[0].delta.content
            if new_token:
                self.response_fragment += new_token
                logger.info(f'self.response_fragment: {self.response_fragment}, new_token: {new_token=}')

                if self.in_metadata: # 表情・動作情報の出力中
                    if ">" in self.response_fragment: # 表情・動作情報が完全に出力された
                        parts = self.response_fragment.split(">", 1)
                        self.response_fragment = parts[1]
                        self.in_metadata = False
                        return _parse_split(parts[0])

                else:
                    match = self.punctuation_pattern.search(self.response_fragment)
                    if match:
                        # 句読点がある場合
                        parts = self.response_fragment.split(match.group(0), 1)
                        self.response_fragment = parts[1]
                        return {"phrase": parts[0]}

                    if "<" in self.response_fragment:
                        parts = self.response_fragment.split("<", 1)
                        if parts[0]: # <の前にテキストがある場合
                            self.response_fragment = "<" + parts[1]
                            return {"phrase": parts[0]}
                        self.response_fragment = parts[1]
                        self.in_metadata = True
                            
        # ストリームの最後に残った断片を返す
        if self.response_fragment:
            fragment_to_return = self.response_fragment
            self.response_fragment = ""
            if not self.in_metadata and fragment_to_return.strip():
                 return {"phrase": fragment_to_return}

        raise StopIteration
   
    # ResponseGeneratorをイテレータ化
    def __iter__(self):
        return self

class ResponseChatGPT():
    def __init__(self, config, system_prompt):
        self.config = config
        self.system_prompt = system_prompt

        self.dialogue_history = [{"role": "system", "content": self.system_prompt}]

        # 入力されたユーザ発話に関する情報を保持する変数
        self.user_utterance = ''
        self.response = ''
        self.last_asr_iu_id = ''
        self.asr_time = 0.0
    
    # LLMの呼び出しを開始
    def run(self, asr_timestamp, user_utterance, last_asr_iu_id, parent_llm_buffer):
        self.user_utterance = user_utterance
        self.last_asr_iu_id = last_asr_iu_id
        self.asr_time = asr_timestamp

        if user_utterance:
            # 対話履歴に追加
            self.dialogue_history.append({"role": "user", "content": user_utterance})
        

        # Generaterを対話履歴で初期化
        self.response = ResponseGenerator(self.config, self.dialogue_history, user_utterance)
        parent_llm_buffer.put(self)

    # システム応答を対話履歴に追加
    def add_assistant_response(self, full_response):
        # メタデータ（<...>）を除外して履歴に追加
        cleaned_response = re.sub(r'<[^>]*>', '', full_response)
        if cleaned_response:
             self.dialogue_history.append({"role": "assistant", "content": full_response})

import threading
import queue
import yaml

 # YAML形式の設定ファイル読み込み関数
def load_config(config_filename):
    with open(config_filename, encoding='utf-8') as f:
        config = yaml.safe_load(f)
    return config

if __name__ == "__main__":
    # test
    openai.api_key = ''    
    config = load_config('../config/config.yaml')

    asr_timestamp = time.time()
    query = 'そうですか、作業療法はリハビリの一種です。'
    dialogue_history = [
        {'role': 'user', 'content': "こんにちは"},
        {'role': 'assistant', 'content': "こんにちは。/0_平静,2_うなずく"},
        {'role': 'user', 'content': "本日は作業療法を行います。作業療法について何かご存知ですか？"},
        {'role': 'assistant', 'content': "いいえ、あまりよく知りません。/4_考え中,3_首をかしげる"},
    ]
    llm_buffer = queue.Queue()
    llm = ResponseChatGPT(config, None)
    t = threading.Thread(
        target=llm.run,
        args=(time.time(),
                query,
                None,
                llm_buffer)
    )
    t.start()
    for part in llm_buffer.get().response:
        print(part)
    time.sleep(0.5)
