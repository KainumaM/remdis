import logging
import os

# 新しいログレベル DIALOGUE を定義
DIALOGUE_LEVEL_NUM = 25  # INFO (20) と WARNING (30) の間に設定

logging.addLevelName(DIALOGUE_LEVEL_NUM, "DIALOGUE")

def dialogue(self, message, *args, **kwargs):
    if self.isEnabledFor(DIALOGUE_LEVEL_NUM):
        self._log(DIALOGUE_LEVEL_NUM, message, args, **kwargs)

logging.Logger.dialogue = dialogue

# ロガーを取得
logger = logging.getLogger("DialogueLogger")
logger.setLevel(logging.DEBUG)  # 全てのログレベルを処理するために DEBUG に設定

# ログディレクトリが存在しない場合は作成
log_directory = "./logs"
if not os.path.exists(log_directory):
    os.makedirs(log_directory)

# ファイルハンドラ1: DIALOGUE レベルのみをファイルに書き込む
dialogue_file = os.path.join(log_directory, "dialogue.log")
dialogue_file_handler = logging.FileHandler(dialogue_file, mode="a", encoding="utf-8")
dialogue_file_handler.setLevel(DIALOGUE_LEVEL_NUM)
dialogue_file_handler.addFilter(lambda record: record.levelno == DIALOGUE_LEVEL_NUM)
dialogue_file_handler.setFormatter(logging.Formatter("%(message)s"))

# ファイルハンドラ2: DIALOGUE レベルと INFO レベルをファイルに書き込む
info_dialogue_file = os.path.join(log_directory, "info_and_dialogue.log")
info_dialogue_file_handler = logging.FileHandler(info_dialogue_file, mode="a", encoding="utf-8")
info_dialogue_file_handler.setLevel(logging.INFO)
info_dialogue_file_handler.addFilter(lambda record: record.levelno in (logging.INFO, DIALOGUE_LEVEL_NUM))
info_dialogue_file_handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))

# コンソールハンドラ: DIALOGUE レベルと INFO レベルを標準出力に出力する
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_handler.addFilter(lambda record: record.levelno in (logging.INFO, DIALOGUE_LEVEL_NUM))
console_handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))

# ハンドラをロガーに追加
logger.addHandler(dialogue_file_handler)
logger.addHandler(info_dialogue_file_handler)
logger.addHandler(console_handler)

# サードパーティライブラリのログレベルを制御
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("openai").setLevel(logging.WARNING)


if __name__ == "__main__":
    # ログのテスト出力
    logger.debug("これはデバッグメッセージです")
    logger.info("これは情報メッセージです")
    logger.dialogue("これはダイアログメッセージです")
    logger.warning("これは警告メッセージです")
    logger.error("これはエラーメッセージです")
    logger.critical("これは重大なエラーメッセージです")

    
