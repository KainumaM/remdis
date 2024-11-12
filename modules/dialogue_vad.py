import sys
import threading
import queue
import time
import re
import argparse

from base import RemdisModule, RemdisState, RemdisUtil, RemdisUpdateType
from llm import ResponseChatGPT
import prompt.util as prompt_util
from logger import logger


class Dialogue(RemdisModule):
    def __init__(self, 
                 assistant_id,
                 pub_exchanges=['dialogue', 'dialogue2'],
                 sub_exchanges=['asr', 'vap', 'tts', 'bc', 'emo_act']):
        super().__init__(pub_exchanges=pub_exchanges,
                         sub_exchanges=sub_exchanges)

        # 設定の読み込み
        self.history_length = self.config['DIALOGUE']['history_length']
        self.response_generation_interval = self.config['DIALOGUE']['response_generation_interval']
        self.prompts = prompt_util.load_prompts(self.config['ChatGPT']['prompts'])

        # 対話履歴
        self.dialogue_history = []

        # assistant_id を格納
        self.assistant_id = assistant_id


        # IUおよび応答の処理用バッファ
        self.system_utterance_end_time = 0.0
        self.input_iu_buffer = queue.Queue()
        self.bc_iu_buffer = queue.Queue()
        self.emo_act_iu_buffer = queue.Queue()
        self.output_iu_buffer = []
        self.llm_buffer = queue.Queue()

        # 対話状態管理
        self.event_queue = queue.Queue()
        self.state = 'idle'
        self._is_running = True

        # IU処理用の関数
        self.util_func = RemdisUtil()

        # 受信したIUを保持しておく変数
        self.iu_memory = []

    # メインループ
    def run(self):
        # 音声認識結果受信スレッド
        t1 = threading.Thread(target=self.listen_asr_loop)
        # 音声合成結果受信スレッド
        t2 = threading.Thread(target=self.listen_tts_loop)
        # ターンテイキングイベント受信スレッド
        t3 = threading.Thread(target=self.listen_vap_loop)
        # 相槌生成結果受信スレッド
        t4 = threading.Thread(target=self.listen_bc_loop)
        # 表情・行動情報受信スレッド
        t5 = threading.Thread(target=self.listen_emo_act_loop)
        # 逐次応答生成スレッド
        t6 = threading.Thread(target=self.parallel_response_generation)
        # 状態制御スレッド
        t7 = threading.Thread(target=self.state_management)
        # 表情・行動制御スレッド
        t8 = threading.Thread(target=self.emo_act_management)

        # スレッド実行
        t1.start()
        t2.start()
        t3.start()
        t4.start()
        t5.start()
        t6.start()
        t7.start()
        t8.start()

    # 音声認識結果受信用のコールバックを登録
    def listen_asr_loop(self):
        self.subscribe('asr', self.callback_asr)

    # 音声合成結果受信用のコールバックを登録
    def listen_tts_loop(self):
        self.subscribe('tts', self.callback_tts)

    # VAP情報受信用のコールバックを登録
    def listen_vap_loop(self):
        self.subscribe('vap', self.callback_vap)

    # バックチャネル受信用のコールバックを登録
    def listen_bc_loop(self):
        self.subscribe('bc', self.callback_bc)

    # 表情・行動情報受信用のコールバックを登録
    def listen_emo_act_loop(self):
        self.subscribe('emo_act', self.callback_emo_act)

    # 随時受信される音声認識結果の格納
    def parallel_response_generation(self):
        while True:
            # IUを受信して保存
            input_iu = self.input_iu_buffer.get()
            self.iu_memory.append(input_iu)
            
            # IUがREVOKEだった場合はメモリから削除
            if input_iu['update_type'] == RemdisUpdateType.REVOKE:
                self.iu_memory = self.util_func.remove_revoked_ius(self.iu_memory)
           

    # 対話状態を管理
    def state_management(self):
        while True:
            # イベントに応じて状態を遷移
            event = self.event_queue.get()
            prev_state = self.state
            self.state = RemdisState.transition[self.state][event]
            logger.info(f'********** State: {prev_state} -> {self.state}, Trigger: {event} **********')
            
            # 直前の状態がtalkingの場合にイベントに応じて処理を実行
            if prev_state == 'talking':
                if event == 'SYSTEM_BACKCHANNEL':
                    pass
                if event == 'USER_BACKCHANNEL':
                    pass
                if event == 'USER_TAKE_TURN':
                    self.stop_response()
                if event == 'BOTH_TAKE_TURN':
                    self.stop_response()
                if event == 'TTS_COMMIT':
                    self.stop_response()
                
            # 直前の状態がidleの場合にイベントに応じて処理を実行
            elif prev_state == 'idle':
                if event == 'SYSTEM_BACKCHANNEL':
                    self.send_backchannel()
                if event == 'SYSTEM_TAKE_TURN':
                    self.send_response()
                if event == 'ASR_COMMIT':
                    self.send_response()

    # 表情・感情を管理
    def emo_act_management(self):
        while True:
            iu = self.emo_act_iu_buffer.get()
            # 感情または行動の送信
            expression_and_action = {}
            if 'emotion' in iu['body']:
                expression_and_action['expression'] = iu['body']['emotion']
            if 'action' in iu['body']:
                expression_and_action['action'] = iu['body']['action']
            
            if expression_and_action:
                snd_iu = self.createIU(expression_and_action, 'dialogue2', RemdisUpdateType.ADD)
                snd_iu['data_type'] = 'expression_and_action'
                self.printIU(snd_iu)
                self.publish(snd_iu, 'dialogue2')


    # システム発話を送信
    def send_response(self):
        # ユーザ発話を受信
        user_utterance = self.util_func.concat_ius_body(self.iu_memory)
        if user_utterance == '' or user_utterance == None:
            logger.info("BOTH_SILENCE")
            self.event_queue.put('BOTH_SILENCE')
            return
        
        # 応答生成
        llm = ResponseChatGPT(self.config, self.prompts)
        t = threading.Thread(
            target=llm.run,
            args=(
                time.time(),
                self.assistant_id,
                user_utterance,
                None,
                self.llm_buffer,
            )
        )
        t.start()
        self.llm_buffer.get()

        # 生成内容をIUに分割して送信
        conc_response = ''
        for part in llm.response: 
            # 表情・動作情報の処理
            expression_and_action = {}
            if 'expression' in part and part['expression'] != 'normal':
                expression_and_action['expression'] = part['expression']
            if 'action' in part and part['action'] != 'wait':
                expression_and_action['action'] = part['action']
            if expression_and_action:
                snd_iu = self.createIU(expression_and_action, 'dialogue2', RemdisUpdateType.ADD)
                snd_iu['data_type'] = 'expression_and_action'
                self.printIU(snd_iu)
                self.publish(snd_iu, 'dialogue2')
                self.output_iu_buffer.append(snd_iu)
            # 発話情報の処理
            if 'phrase' in part:
                if self.state == 'talking':
                    snd_iu = self.createIU(part['phrase'], 'dialogue', RemdisUpdateType.ADD)
                    self.printIU(snd_iu)
                    self.publish(snd_iu, 'dialogue')
                    self.output_iu_buffer.append(snd_iu)
                    conc_response += part['phrase']

        # 対話履歴に発話を追加
        if llm.user_utterance:
            logger.dialogue(f'User   : {llm.user_utterance}')
        logger.dialogue(f'System : {conc_response}')

        # 応答生成終了メッセージ
        snd_iu = self.createIU('', 'dialogue', RemdisUpdateType.COMMIT)
        self.printIU(snd_iu)
        self.publish(snd_iu, 'dialogue')

        # 音声認識のバッファをクリア
        self.iu_memory = []

    # バックチャネルを送信
    def send_backchannel(self):
        iu = self.bc_iu_buffer.get()

        # 現在の状態がidleの場合のみ後続の処理を実行してバックチャネルを送信
        if self.state != 'idle':
            return

        # 相槌の送信
        snd_iu = self.createIU(iu['body']['bc'], 'dialogue', RemdisUpdateType.ADD)
        self.printIU(snd_iu)
        self.publish(snd_iu, 'dialogue')

    # 応答を中断
    def stop_response(self):
        for iu in self.output_iu_buffer:
            iu['update_type'] = RemdisUpdateType.REVOKE
            self.printIU(iu)
            self.publish(iu, iu['exchange'])
        self.output_iu_buffer = []

    # 音声認識結果受信用のコールバック
    def callback_asr(self, ch, method, properties, in_msg):
        in_msg = self.parse_msg(in_msg)
        self.input_iu_buffer.put(in_msg)
            
    # 音声合成結果受信用のコールバック
    def callback_tts(self, ch, method, properties, in_msg):
        in_msg = self.parse_msg(in_msg)
        if in_msg['update_type'] == RemdisUpdateType.COMMIT:
            self.output_iu_buffer = []
            self.system_utterance_end_time = in_msg['timestamp']
            self.event_queue.put('TTS_COMMIT')

    # VAP情報受信用のコールバック
    def callback_vap(self, ch, method, properties, in_msg):
        in_msg = self.parse_msg(in_msg)
        self.event_queue.put(in_msg['body'])

    # バックチャネル受信用のコールバック
    def callback_bc(self, ch, method, properties, in_msg):
        in_msg = self.parse_msg(in_msg)
        self.bc_iu_buffer.put(in_msg)
        self.event_queue.put('SYSTEM_BACKCHANNEL')

    # 表情・行動情報受信用のコールバック
    def callback_emo_act(self, ch, method, properties, in_msg):
        in_msg = self.parse_msg(in_msg)
        self.emo_act_iu_buffer.put(in_msg)

    # 対話履歴を更新
    def history_management(self, role, utt):
        self.dialogue_history.append({"role": role, "content": utt})
        if len(self.dialogue_history) > self.history_length:
            self.dialogue_history.pop(0)

def main():
    assistant_ids = {
        # assistant_name, chatgpt_id, voicevox_id
        "asada": ("asst_z2nd92qpkV3ktiTDMMwwZEnG", 2),
        "suzuki": ("asst_z2nd92qpkV3ktiTDMMwwZEnG", 2),
        "okada": ("asst_z2nd92qpkV3ktiTDMMwwZEnG", 41),
        "sakamoto": ("asst_z2nd92qpkV3ktiTDMMwwZEnG", 41),
        "tanaka": ("asst_z2nd92qpkV3ktiTDMMwwZEnG", 41),
    }
    assistant_names = list(assistant_ids.keys())

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "assistant",
        type=str,
        choices=assistant_names,
        help=f"対話相手の名前を指定します。利用可能な対話相手は、{', '.join(assistant_names)} です。",
    )
    args = parser.parse_args()

    print("Selected assistant:", args.assistant)
    assistant_id, _ = assistant_ids[args.assistant]

    dialogue = Dialogue(assistant_id=assistant_id)
    dialogue.run()

if __name__ == '__main__':
    main()
