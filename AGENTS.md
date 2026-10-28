# StayActive public repository

- 公開用の操作には GitHub アカウント `tomonariworks`（user ID `223291788`）だけを使う。Organization の管理権限を持っていても、別の個人アカウントを使ってはならない。
- 公開先は `Tomonari-Works/StayActive`。他の非公開プロジェクトやグローバルな GitHub 認証設定は変更しない。
- GitHub の書き込みには `python tools/public_github.py gh ...`、push には `python tools/public_github.py push <branch>`、fetch には `python tools/public_github.py fetch` を使う。このヘルパーは公開専用プロファイルと認証済み user ID を検証する。認証に失敗した場合、別アカウントの SSH キーや CLI 認証にフォールバックしない。
- 公開専用のログインは `python tools/public_github.py login`。認証操作はユーザー本人が行う。秘密値や認証トークンを表示・Git 追加しない。
- 新しいコミットの著者・コミッターは `TomonariWorks <223291788+tomonariworks@users.noreply.github.com>` にする。公開済みの正しいブランド名義の履歴は維持する。
- `.idea/`、ショートカット、個人設定、ログ、`.artifacts/`、仮想環境、認証情報を公開しない。stage は公開対象の明示的なファイル一覧で行う。
- リリース前にテスト、配布 EXE の起動確認、第三者ライセンス、公開対象のプライバシー確認を完了する。
- コミュニケーションは日本語。
