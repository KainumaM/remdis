import sys
import json
import time
import re
import string

import openai

from base import MMDAgentEXLabel


class ResponseGenerator:
    def __init__(self, config, asr_timestamp, query, dialogue_history, prompts):
        # 設定の読み込み
        self.max_tokens = config['ChatGPT']['max_tokens']
        self.max_message_num_in_context = config['ChatGPT']['max_message_num_in_context']
        self.model = config['ChatGPT']['response_generation_model']

        # 処理対象のユーザ発話に関する情報
        self.asr_timestamp = asr_timestamp
        self.query = query
        self.dialogue_history = dialogue_history
        self.prompts = prompts

        # 生成中の応答を保持・パースする変数
        self.response_fragment = ''
        self.punctuation_pattern = re.compile('[、。！？]')

        # ChatGPTに入力する対話文脈
        self.messages = []

        # 過去の対話履歴を対話文脈に追加
        i = max(0, len(self.dialogue_history) - self.max_message_num_in_context)
        self.messages.extend(self.dialogue_history[i:])

        # 新しいユーザ発話が存在せず自ら発話する場合のプロンプトを対話文脈に追加
        if query == None or query == '':
           query = "(沈黙)"

        self.log(f"messages: {self.messages=}")
        self.log(f"Call ChatGPT: {query=}")
        
        # threadの初期化と対話履歴の追加
        self.thread = openai.beta.threads.create(
            messages=self.messages
        )

        # ユーザ発話の追加
        message = openai.beta.threads.messages.create(
            thread_id=self.thread.id,
            role="user",
            content=query,
        )

        # ストリーミングリクエストの開始
        self.stream = openai.beta.threads.runs.create(
            assistant_id="asst_z2nd92qpkV3ktiTDMMwwZEnG",
            thread_id=self.thread.id,
            stream=True,
            max_completion_tokens=self.max_tokens
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
        for event in self.stream:
            if event.event == "thread.message.delta" and event.data.delta.content:
                new_token = event.data.delta.content[0].text.value
                self.log(f"new_token: {new_token=}")

                # 応答の断片を追加
                if new_token is not None and new_token != "/":
                    self.response_fragment += new_token

                # 句読点で応答を分割
                splits = self.punctuation_pattern.split(self.response_fragment, 1)
                self.log(f"splits: {splits=}")

                # 次のループのために残りの断片を保持
                self.response_fragment = splits[-1]

                # 句読点が存在していた場合は1つ目の断片を返す
                if len(splits) == 2 or new_token == "/":
                    if splits[0]:
                        return {"phrase": splits[0]}
                
                # 応答の最後が来た場合は残りの断片を返す
                if new_token == "/":
                    if self.response_fragment:
                        return {"phrase": self.response_fragment}
                    self.response_fragment = ''

                self.log(f"splited: {splits=}")

            elif event.event == "thread.message.completed":
                # ChatGPTの応答が完了した場合は残りの断片をパースして返す
                print(event.data.content[0].text.value)
                
                agent_move = event.data.content[0].text.value.split("/")
                self.log(f"thread.message.completed: {agent_move=}")

                if len(agent_move) > 1:
                    return _parse_split(agent_move[1])

        raise StopIteration
    
    # ResponseGeneratorをイテレータ化
    def __iter__(self):
        return self

    # デバッグ用のログ出力
    def log(self, *args, **kwargs):
        print(f"[{time.time():.5f}]", *args, flush=True, **kwargs)


class ResponseChatGPT():
    def __init__(self, config, prompts):
        self.config = config
        self.prompts = prompts

        # 設定の読み込み
        openai.api_key = config['ChatGPT']['api_key']

        # 入力されたユーザ発話に関する情報を保持する変数
        self.user_utterance = ''
        self.response = ''
        self.last_asr_iu_id = ''
        self.asr_time = 0.0
    
    # ChatGPTの呼び出しを開始
    def run(self, asr_timestamp, user_utterance, dialogue_history, last_asr_iu_id, parent_llm_buffer):
        self.user_utterance = user_utterance
        self.last_asr_iu_id = last_asr_iu_id
        self.asr_time = asr_timestamp

        # ChataGPTを呼び出して応答の生成を開始
        self.response = ResponseGenerator(self.config, asr_timestamp, user_utterance, dialogue_history, self.prompts)

        # 自身をDialogueモジュールが持つLLMバッファに追加
        parent_llm_buffer.put(self)


if __name__ == "__main__":
    openai.api_key = ''

    config = {'ChatGPT': {
        'max_tokens': 64,
        'max_message_num_in_context': 3,
        'response_generation_model': 'gpt-3.5-turbo'
    }}

    asr_timestamp = time.time()
    query = 'そうですか、作業療法はリハビリの一種です。'
    dialogue_history = [
        {'role': 'user', 'content': "こんにちは"},
        {'role': 'assistant', 'content': "こんにちは。/0_平静,2_うなずく"},
        {'role': 'user', 'content': "本日は作業療法を行います。作業療法について何かご存知ですか？"},
        {'role': 'assistant', 'content': "いいえ、あまりよく知りません。/4_考え中,3_首をかしげる"},
    ]
    prompts = {}

    # with open('./prompt/response.txt') as f:
    #     prompts['RESP'] = f.read()

    response_generator = ResponseGenerator(config, asr_timestamp, query, dialogue_history, prompts)

    for part in response_generator:
        response_generator.log(part)

    ##############

    time.sleep(0.5)

    # dialogue_history2 = [
    #     {'role': 'user', 'content': "こんにちは"},
    #     {'role': 'assistant', 'content': "こんにちは"},
    #     {'role': 'user', 'content': "本日は作業療法を行います。作業療法について何かご存知ですか？"},
    #     {'role': 'assistant', 'content': "いいえ、あまりよく知りません。"},               
    #     {'role': 'user', 'content': "そうですか、作業療法はリハビリの一種です。"},
    #     {'role': 'assistant', 'content': "そうなんですね、知りませんでした。"},
    # ]
    # query = 'それでは早速始めていきますね。'
    # response_generator2 = ResponseGenerator(config, asr_timestamp, query, dialogue_history2, prompts)

    # for part in response_generator2:
    #     response_generator.log(part)