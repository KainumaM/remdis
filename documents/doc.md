# ドキュメント

# MMDAgent-Ex

## エージェントの切り替え
example の main.fst のモデルファイル Gene.pmd をしているところを以下のように変更して起動しなおし

```code:fst
<eps> MODEL_ADD|0|asset/models/<model_name>/<model_name>.pmd
```

## Uka, Gene 以外のエージェントを使用するには
MMDAgent-ExはMikuMikuDance形式の3Dモデルをサポートしているらしく、そのモデルをインポートすれば使える[^1]

参考
- https://www.youtube.com/watch?v=QnI07mXvQSc&ab_channel=GROOVY%5BK%5D2000

モデルの探し先
- booth: https://booth.pm/en/browse/3D%20Models?q=MikuMikuDance
- bowlroll: https://bowlroll.net/file/tag/MikuMikuDance
- deviantart: https://www.deviantart.com/tag/mikumikudance

### .pmxファイルから .pmd, .pmd.csv ファイルへの変換
pmxファイルはサポートされてないので変換が必要。変換にpmxエディタが必要なのでインストールする。\
起動しない場合は必要モジュールがない可能性（自分はdirectXのランタイムがなかった）\
変換時にいくらかのデータが失われる可能性アリ（表情とか）

参考
- http://rockstababy.starfree.jp/mmdsupporter/bemmder/section1.php
- https://mmdagent-ex.dev/ja/docs/change-model/
- https://mmdagent-ex.dev/docs/pmx/

# ライセンス

- [remdisソースコード](https://github.com/remdis/remdis) : Apache2.0
- [ttslearn（音声合成）](https://github.com/r9y9/ttslearn) : MIT
- [googole-cloud-speech](https://pypi.org/project/google-cloud-speech/) : Apache2.0
- [OpanAI pythonライブラリ](https://github.com/openai/openai-python) : MIT
- [MMDAgent-Ex](https://mmdagent-ex.dev/ja/docs/license-and-guideline/) : Apache2.0
  - [CG Avator Gene](https://github.com/mmdagent-ex/gene/blob/main/README.ja.md) : CC-BY4.0
  - [CG Avator Uka](https://github.com/mmdagent-ex/uka/blob/main/README.ja.md) : CC-BY4.0
  - [CG Avator KuronoTakehiro](https://booth.pm/en/items/3520385) : 注意が必要


