# Contributing

バグ報告は OS、StayActive のバージョン、再現手順、期待する結果、実際の結果を添えて Issue に記載してください。API キー、認証情報、個人設定ファイル、個人情報を含むログは公開しないでください。

変更前にプロジェクト専用の仮想環境へ `requirements.txt` をインストールし、`python -m unittest discover -v` と `python main.py --smoke-test` を実行してください。Windows の配布ファイルは `build.bat` で作成・起動検証します。OS 入力やスリープ抑止を実際に実行する検証は、単体テストの模擬バックエンドと分けてください。

第三者ライセンスを変更した場合は `THIRD_PARTY_NOTICES.md` と Qt の正確なバージョンの通知を更新してください。依存の固定、ビルド情報、配布ファイルの出所が一致することを確認します。

メンテナーの公開操作は `AGENTS.md` のアカウント規則に従い、`tools/public_github.py` を使用してください。認証失敗時は他の認証へ切り替えず停止します。
