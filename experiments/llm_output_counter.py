
import os
import time
import csv
import yaml
from collections import Counter
from openai import OpenAI


# ==========================================
# 設定
# ==========================================

LLM_URL = "http://192.168.1.160:8000/v1"
MODEL_NAME = "Qwen/Qwen2.5-14B-Instruct-GPTQ-Int8"

PROMPT_NAME = "watanabe"

NUM_REQUESTS = 100

OUTPUT_FILE = "response_results.csv"


# ==========================================
# ファイル読み込み
# ==========================================

def load_prompt(prompt_name):
    file_path = os.path.join(
        "LLM_prompts", f"{prompt_name}.txt"
    )

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        print(f"[ERROR] プロンプト読み込み失敗: {e}")
        raise


def load_config(config_filename):
    try:
        with open(config_filename, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except Exception as e:
        print(f"[WARNING] 設定読み込み失敗: {e}")
        return {"ChatGPT": {"max_tokens": 512}}


# ==========================================
# LLMへのリクエスト
# ==========================================

def generate_response(client, messages, max_tokens):

    stream = client.chat.completions.create(
        model=MODEL_NAME,
        messages=messages,
        stream=True,
        max_tokens=max_tokens,
        temperature=0.5

    )

    response = ""

    for chunk in stream:
        if not chunk.choices:
            continue

        token = chunk.choices[0].delta.content

        if token:
            response += token

    return response


# ==========================================
# 集計結果の保存
# ==========================================

def save_results(response_counts, filename):

    sorted_results = response_counts.most_common()

    with open(filename, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)

        writer.writerow(["出力内容", "出現回数"])

        for response, count in sorted_results:
            writer.writerow([response, count])

    print(f"\n[INFO] 集計結果を保存しました: {filename}")


# ==========================================
# メイン処理
# ==========================================

def main():

    config = load_config("config/config.yaml")
    system_prompt = load_prompt(PROMPT_NAME)

    max_tokens = config.get("ChatGPT", {}).get(
        "max_tokens", 512
    )

    client = OpenAI(
        base_url=LLM_URL,
        api_key="dummy",
        timeout=20.0
    )

    # 全リクエストで同じメッセージを使用
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": "こんにちは"},
        {"role": "assistant", "content":  "こんにちは。渡辺です。よろしくお願いします。<0_平静,2_うなずく>"},
        {"role": "user", "content": "よろしくお願いします。"},
    ]

    response_counts = Counter()
    error_count = 0

    print("=" * 60)
    print(f"リクエスト回数: {NUM_REQUESTS}")
    print("=" * 60)

    start_time = time.time()

    for i in range(NUM_REQUESTS):

        print(f"\n[{i + 1}/{NUM_REQUESTS}] リクエスト送信中...")

        try:
            response = generate_response(
                client,
                messages,
                max_tokens
            )

            response_counts[response] += 1

            print(f"応答: {response}")

        except Exception as e:
            error_count += 1
            print(f"[ERROR] リクエスト失敗: {e}")

    elapsed_time = time.time() - start_time

    # ======================================
    # 集計結果
    # ======================================

    print("\n" + "=" * 60)
    print("集計結果")
    print("=" * 60)

    for response, count in response_counts.most_common():
        print(f"\n出現回数: {count}")
        print(f"出力内容: {response}")
        print("-" * 60)

    print(f"\n総リクエスト数: {NUM_REQUESTS}")
    print(f"成功数: {NUM_REQUESTS - error_count}")
    print(f"失敗数: {error_count}")
    print(f"異なる応答の種類: {len(response_counts)}")
    print(f"実行時間: {elapsed_time:.2f} 秒")

    save_results(response_counts, OUTPUT_FILE)


if __name__ == "__main__":
    main()
