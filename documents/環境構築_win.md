# 環境構築_win

前提条件として WSL2 が設定済みであること


## Docker Desktop Install

下記からインストール\
https://docs.docker.com/desktop/setup/install/windows-install/

インストールしたら設定からエンジンを WSL2 のディストロを参照するように


## 各種API認証情報の設定

GCP
 - credentials のファイルを持ってきて任意の場所（config.yamlで設定）に置く

ChatGPT
- APIキーをconfig.yamlに設定


## VSCode Install

プログラム実行に使うので、あらかじめインストール\
[Python の拡張機能](https://marketplace.visualstudio.com/items?itemName=ms-python.python)をインストールする


## Anaconda Install

下記からインストール\
インストール時にcondaのPATHを設定するようにする\
https://www.anaconda.com/download/success


cmd を開いて下記実行
```cmd
$ conda create -n [name] python=[version]
$ conda activate [name]	
```
Anaconda でよく使うコマンド一覧\
https://qiita.com/naz_/items/84634fbd134fbcd25296


VSCodeからデフォルトの環境を設定\
https://code.visualstudio.com/docs/python/environments#_creating-environments


## 必要pipモジュールのインストール

`pip install -r requirements.txt`する前に必要なアプリケーションをインストール
- cmake
  - https://cmake.org/download/
  - Binary distributions から適当なバージョンをインストール
- Visual Studio Build Tools
  - https://visualstudio.microsoft.com/ja/visual-cpp-build-tools/
  - インストール時に「C++によるデスクトップ開発」を選択し、C++コンパイラを含める

実行
```cmd
pip install -r requirements.txt
```
