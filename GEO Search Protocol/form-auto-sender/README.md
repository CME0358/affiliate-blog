# フォーム自動送信（form-auto-sender）

営業リスト（Markdown）から問い合わせフォームを探索し、文面を送信するツール群です。  
詳細な日常運用手順は別ドキュメントに従ってください。

## 運用ダッシュボード（`build_ops_dashboard.py`）

Vault の `70_outputs/運用ダッシュボード.html` に、リスト獲得数・本日の送信試行/成功/エラー・`error.csv` 累計・累計成功送信などを書き出す。

```bash
cd "/path/to/form-auto-sender"
python3 build_ops_dashboard.py
```

**1 時間ごとに自動更新**するには `launchd/com.coaretail.ops-dashboard.plist` を `~/Library/LaunchAgents/` にコピーして `launchctl load`（詳細は plist 先頭コメント）。`StartInterval` は 3600 秒。

**指標の出所**

| 表示名 | データ源 |
| --- | --- |
| リスト獲得数 | `config.INPUT_DIR`（`40_Sales/商談メモ/リスト`）内の `*.md` を `parse_md_list` で集計 |
| 本日送信試行数 / 成功 / 手動確認 / エラー（ログ） | 当日 `logs/YYYY-MM-DD.md` の各セクション内 `###` 件数（`log_manager.get_stats`） |
| error.csv 累計 / 最多・次点理由 | `logs/error.csv`（CSV として正しく行カウント） |
| 累計成功送信 | `logs/.sent_index.csv` のデータ行数 |

HTML のテンプレートは `templates/ops_dashboard.html`。生成結果を確認したらブラウザで **再読み込み** する。

## フォーム探索（form_finder.py）

- リンクに加え **`<iframe src>`** もスキャン
- LINE・ホットペッパー等のみのサイトは `no_form_external_booking` でスキップ
- PDF/Office 直リンクは `pdf_or_file_download`（`error`）
- ページ読み込み: `domcontentloaded` + **2秒待機**（timeout 15秒）
- 最終手段: Google 検索「{会社名} お問い合わせ」（`ENABLE_GOOGLE_FORM_SEARCH`、既定 ON）

### ハング対策（2026-05-19）

| 設定 | 既定値 | 意味 |
| --- | --- | --- |
| `FORM_FIND_TOTAL_TIMEOUT_SEC` | 120 | 1社あたり探索の全体上限（秒） |
| `FORM_FIND_MAX_NAVIGATIONS` | 28 | ページ遷移の最大回数 |
| `FORM_FIND_MAX_LINK_FOLLOWS` | 8 | リンク辿り上限 |
| `CHAIN_SITE_MAX_NAVIGATIONS` | 12 | チェーン本部（s-b-c.net 等）の遷移上限 |
| `FORM_FIND_MAX_GOOGLE_FOLLOWS` | 3 | Google 検索後に辿る URL 上限 |

チェーン店舗 URL は店舗リンク総なめ・Google 検索をスキップし、`no_form_chain_site` で短時間終了します。

## フォーム解析の API コスト削減

`form_sender.py` はフィールド解決を次の順で行い、Claude API 呼び出しを最小化します。

| 順 | 方式 | 説明 |
| --- | --- | --- |
| 1 | **キャッシュ** | `logs/form_field_cache.json`（`form_url` キー・TTL 90日） |
| 2 | **DOM ルール** | Playwright で `input` / `textarea` の name・label からセレクタ推定（API 不要） |
| 3 | **Claude** | 上記で不足時のみ。HTML は `<form>` 周辺に限定（最大 12,000 文字） |

本番ログに `📋 フィールド解決: cache|dom|claude` が出力されます。

## リスト前処理・別チャネル振り分け（P0）

`main.py` 実行時、`list_filter.py` が送信キューから以下を自動除外し、別チャネルへ記録します。

| 条件 | 理由 | 出力先 |
| --- | --- | --- |
| Web URL なし | `website_url_is_none` | `logs/alternate_channel.csv` |
| LINE / SNS URL | `list_filter_sns_only` | 同上 + `40_Sales/商談メモ/リスト/別チャネル/` |
| 予約専用 URL | `list_filter_reservation_url` | 同上 |

`--retry-errors` 時はフィルタをスキップ（既知の失敗を再処理するため）。

## reCAPTCHA 手動キュー（P0）

本番 `main.py` 完了後、当日の pending を Markdown に出力します。

```bash
python3 export_pending.py
python3 export_pending.py --date 2026-05-18
```

出力: `70_outputs/営業/YYYY-MM-DD_reCAPTCHA手動送信キュー.md`

## 失敗クールダウン（P0）

同一企業の **毎日再試行** と `error.csv` の水増しを防ぐ。

- 索引: `logs/.failure_cooldown.csv`
- 本番 `main.py` 実行時: クールダウン中は `⏭️ スキップ（失敗クールダウン）` で処理しない
- 理由別の再試行までの日数は `config.py` の `FAILURE_COOLDOWN_DAYS`（例: フォーム未検出30日、submit失敗7日）

**既存 error.csv から索引を作る（初回のみ）**

```bash
python3 backfill_failure_cooldown.py
```

**クールダウンを無視して再処理**

```bash
python main.py --retry-errors --force-retry
```

## フォーム探索（`form_finder.py`）

- **チェーン店舗（P1）**: 店舗URLの場合、**本部 `/contact` 等を店舗ページより先**に試行。見つからなければルート・親パスを再探索してから `no_form_chain_site` を記録します。
- **外部フォーム（P1）**: `form.run` / Google Forms / form-mailer 等の外部ホストリンクも問い合わせ候補として採用します。
- **予約フォーム除外**: URL またはページタイトル・`h1` に予約系キーワードがあるページは、問い合わせフォーム URL として**採用しません**。別の問い合わせページを探し、見つからない場合は `error.csv` の理由に **`no_contact_form_only_reservation`** が記録されます。
- **手動除外リスト**: 誤送信などで送信済み扱いを取り消した企業は **`logs/manually_excluded.csv`** に1行追記します（監査用）。**重複送信防止**は `main.py` が更新する **`logs/.sent_index.csv`** から該当行を削除すると効きます（`logs/sent.csv` は環境によって存在しない場合があります）。
- **URL が除外対象か確認**（Playwrightでタイトル・h1も取得）:

```bash
python form_finder.py --check-url "https://example.com/reservation"
```

## イレギュラー対応：エラー再実行手順

通常の `main.py` スケジュール実行とは**別**に、`logs/error.csv` に残した失敗分だけを指定日で再処理できます。

### `retry_errors.py`（手動）

- **対象**: `logs/error.csv` のうち、`logged_date`（列名が `date` の CSV でも可）が **`--date` と一致する行だけ**。
- **スキップ**: `logs/sent.csv` が存在する場合はその内容に加え、**`main.py` が送信成功時に更新する `logs/.sent_index.csv` も参照**し、一致する企業は再送しません。
- **ログ**: 既定では `logs/retry_<フィルタ日付>.log`（例: `--date 2026-05-13` なら `logs/retry_2026-05-13.log`）へ追記。
- **当日の MD ログ**: 再送成功・再失敗・reCAPTCHA などは従来どおり `log_result` 経由で当日の `logs/YYYY-MM-DD.md` と `error.csv` 等へも反映されます。

```bash
cd "/path/to/form-auto-sender"
python retry_errors.py --date 2026-05-13
```

ログファイルだけ変えたい場合:

```bash
python retry_errors.py --date 2026-05-13 --log-file logs/my_retry_run.log
```

完了時に標準出力へ次の形式でサマリーが出ます。

`再実行完了: 送信XX件 / エラーXX件 / スキップXX件`

（「エラー」にはフォーム未取得・送信失敗・reCAPTCHA による保留など、自動ですべき処理が終わらなかった件が含まれます。）

---

### Mac（launchd）：翌朝 10:00 に 1 回だけ実行する例

リポジトリ内の **`launchd/com.coaretail.retry-errors.plist`** をコピーして使います。

1. **編集**（テキストエディタで開く）
   - `WorkingDirectory` … このフォルダ（`form-auto-sender`）の**絶対パス**
   - `StandardOutPath` / `StandardErrorPath` … 同様にプロジェクトの `logs/` への絶対パス（任意で変更可）
   - `StartCalendarInterval` の `Month` / `Day` / `Hour` / `Minute` … **実行したい「翌朝」の暦**
   - `ProgramArguments` の `bash -lc` の文字列内 …  
     `retry_errors.py --date 'YYYY-MM-DD'` の日付を **error.csv に記録されている logged_date** に合わせる

2. **配置**

```bash
cp launchd/com.coaretail.retry-errors.plist ~/Library/LaunchAgents/
```

3. **登録**

```bash
launchctl load ~/Library/LaunchAgents/com.coaretail.retry-errors.plist
```

macOS が新しい環境では次でも登録できます。

```bash
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.coaretail.retry-errors.plist
```

4. **1 回実行後の無効化**

plist 内の `bash -lc` で、ジョブ成功後に **`launchctl unload`** を実行しています（Python が異常終了した場合でも unload が試みられます）。

```bash
launchctl unload ~/Library/LaunchAgents/com.coaretail.retry-errors.plist
```

手動で止める場合も同じです。必要なら plist を削除します。

```bash
rm ~/Library/LaunchAgents/com.coaretail.retry-errors.plist
```

**注意**: `StartCalendarInterval` は**年を指定しない**ため、同じ plist を読み込んだままだと **翌年以降も同じ月日・時刻に再度実行される可能性**があります。今回の運用では実行後に unload 済みなので読み込まれていませんが、検証時は登録解除を忘れないでください。

---

### 通常スケジュールとの関係

- **`main.py` と既存の LaunchAgents／cron は変更していません。**
- `retry_errors.py` は単体で動き、`--date` で絞った `error.csv` の行だけを処理します。
