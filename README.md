# 文学研究のためのデジタル資料活用：メタデータと本文から何がわかるか

講習会「文学研究のためのデジタル資料活用：メタデータと本文から何がわかるか」向け。Open Library / Wikidata / OpenAlex の研究用成果物を参加者に説明するための独立した教材です。

## Open Library Edition集計の進捗

2026年2月28日版のOpen Library Editionsダンプを使用し、
歴史的34,789 Workレコードと補正先3 Work IDを対象に集計しています。

- 抽出されたEditionレコード：421,754件
- 対象OL Work ID：34,792件
- Work別・年代別・言語別集計：作成・整合性検証済み
- Wikidata・OpenAlexとの統合プレビューv4：34,789行、49列

元Edition JSONLと統合プレビューは現時点ではローカル管理です。
GitHub配布用の縮約CSV、再現用スクリプト、テスト、仕様書を管理しています。

Edition件数はOpen Libraryに登録された書誌レコードの観測値であり、
実際の出版部数や出版履歴の完全な記録ではありません。

## 公開状況

このリポジトリでは、講習会用のコード・テスト・仕様書を公開しています。

- Open Library Editionの抽出・集計：検証済み
- Wikidata・OpenAlexとの統合プレビューv4：ローカル生成・検証済み
- 参加者向けCSV：作品メタデータ、英語Edition集計、刊行年別集計を検証済み
- Colabノートブック：ローカル全10コードセルの動作確認済み。Google Colab上では未検証

研究用リポジトリのデータや凍結済み成果物は変更していません。

### 教材の範囲

- Historical Open Library targets: 34,789 source Work records（概念的作品34,789とは異なる）
- Project conceptual Work: v7、active 32,066、identity suspended 16、superseded 7
- Wikidata v6（原判定）: MATCH 8,442 / AMBIGUOUS 358 / NO_MATCH 25,989
- 配布CSVの有効判定: MATCH 8,441 / AMBIGUOUS 358 / NO_MATCH 25,987 / HOLD_TARGET_CORRECTION 3
- OpenAlex integrated v1: 226,214 operational candidate pairs、7,077 Wに少なくとも1件。数値は確定引用数・固有論文総数ではない。
- OpenAlex v1にはR3+A2候補との7ペア差のQC保留がある。オリジナルv1は改変しない。
- Goodreads / UCSD Book Graphは再配布対象外。

## データ生成と再現性

`scripts/` に、Open Library Editionの抽出、出版年解析、
Work別・年代別・言語別集計、歴史的Workへの対応付け、
統合プレビュー生成のコードを収録しています。

`tests/` には人工データによる回帰テストがあります。

大容量のEditionダンプ、抽出済みJSONL、統合プレビューなどの
中間成果物はGit管理から除外しています。
集計の再実行には、対応する入力データが別途必要です。

参加者向けCSVは `data/workshop_search_v1.csv` に配置し、Colabから自動読み込みする設計です。

## 新しい実習Notebook（2冊構成）

従来の `metadata_workshop.ipynb` は残し、
目的別に分割したNotebookを追加しました。

### 01：ブラウザからAPIへ

[`01_publication_history.ipynb`](01_publication_history.ipynb)

Open Libraryのブラウザ画面とAPIを比較し、
取得したEditionを刊行年代・出版社・言語別に集計します。

2026-02-28固定ダンプに基づく多言語集計があるWorkでは、
APIで取得できた範囲と固定集計の違いも確認します。

使用データ：
`data/work_edition_language_year_v1.csv`（187,536行）。

### 02：ダンプから作品集合へ

[`02_work_position.ipynb`](02_work_position.ipynb)

34,789件の固定Work集合を使い、
選択した作品のEdition登録数を同年代の作品群と比較します。

Wikidataの作品同定結果とOpenAlexの暫定候補情報も扱います。
OpenAlexの暫定件数を文学的評価の順位とはみなしません。

### 注意

- 2冊は独立して実行できます。
- APIの一部取得結果を全Editionの分布とみなさないでください。
- 固定集合は英語原作小説の完全な一覧ではありません。
- Edition登録数は売上・読者数を意味しません。
- 実際のGoogle Colab画面での動作確認は公開後に行います。

## 参加者向けColab

ノートブックのコードはローカルで検証済みです。Google Colab上での実行確認は公開後に行います。

`https://colab.research.google.com/github/haruka0221/literary-metadata-workshop-2026/blob/main/metadata_workshop.ipynb`

Googleログイン／ランタイムの接続が必要なことがあります。CSVはこのリポジトリの `data/workshop_search_v1.csv` から自動取得します。

## 参加者向けデータ

### `data/workshop_search_v1.csv`

歴史的Open Library対象34,789レコードを収録した検索用CSV（18列）。

主な情報：

- Open Library：Work ID、タイトル、著者、初刊年の記録、Edition数
- Wikidata：照合判定、採用されたQID
- OpenAlex：暫定候補数、計測単位、品質・照合状態フラグ

OpenAlexの表示値は、次の状態を区別しています。

| フラグ | OL行数 | 意味 |
|---|---:|---|
| `PROVISIONAL` | 32,689 | Project Workに接続済みの暫定候補ペア数 |
| `PROVISIONAL_UNRESOLVED` | 1,673 | 作品同定未確定。Calibration A1/A2 v3の候補ID数を参考表示 |
| `NOT_AVAILABLE` | 410 | 未接続で表示可能な候補数がない |
| `IDENTITY_HOLD` | 17 | 作品同定に問題があり保留 |

`PROVISIONAL` と `PROVISIONAL_UNRESOLVED` は集計経路が異なるため、
数値をそのまま比較ランキングに使用しないでください。

同じProject Workや未解決グループに属する複数のOL Workでは、
同じOpenAlex候補数が繰り返し表示されます。OL行を合算しないでください。

### `data/workshop_english_editions_v1.csv`

34,789 OL Workごとの英語タグ付きEdition集計です。

- 全年代の英語Edition登録数
- 1880〜1950年、1951年以降などの登録数
- 刊行年不明の登録数
- 最も古い英語Editionの観測刊行年

原語が英語の作品だけを選別した表ではありません。

### `data/work_english_edition_by_year_v1.csv`

Work ID × Edition刊行年の英語Edition登録数です。
129,464行で、刊行年不明は `UNKNOWN` として保持しています。

このファイルから出版年代グラフを生成します。
集計対象は2026年2月28日のOpen Library固定ダンプです。

Edition数は印刷部数、売上、読者数を意味しません。
また、刊行年が2027年以降の記録も存在し得るため、
Colabの長期比較グラフは2026年までに制限しています。

### `data/data_dictionary.csv`

上記CSVの18列について、意味と注意点を記載しています。

### `metadata_workshop.ipynb`

Open Library全体のライブ検索、Workの選択、Editionの閲覧、
取得範囲内の言語・刊行年代別グラフを利用できます。

研究用固定集合に含まれるWorkについては、英語Editionの
長期的な刊行年代比較とWikidata・OpenAlexの照合情報も確認できます。

ライブAPIと2026年2月28日版の固定ダンプはデータ時点と収録範囲が異なります。
固定集合は英語原作の小説だけを厳密に選別したものではありません。

### 避けるべき解釈

- 34,789件は34,789の独立した概念的作品を意味しない。
- OLのfirst_publish_yearは概念作品の確定初出年ではない。
- OL登録Edition数は刷数、部数、読者数と一致しない。
- WikidataのNO_MATCHは「実体が存在しない」を意味しない。
- OpenAlexのW×OA候補ペアは引用文献数・本文言及回数・固有学術論文総数ではない。
- identity HOLD と未計測を0扱いしない。
- Project Wで同じ値がOL行に重複するのでOpenAlex列をOL行単位で合計しない。

## 出典・版

- [Open Library](https://openlibrary.org/developers/api) — Work / Edition / Author の書誌レコード、研究用スナップショット等を参照。
- [Wikidata](https://www.wikidata.org/) — 2026-08-05 dumpに由来する研究用照合v6。
- [OpenAlex](https://docs.openalex.org/) — 2026-09-23 Works snapshotを基礎とする integrated_work_visibility_v1。
- [元リポジトリ固定commit](https://github.com/haruka0221/canon-pipeline/tree/dd8ee20393297edfd786fdb3566291fceccb475c)

元サービスの一般的なCC0方針だけで派生CSVの全項目が自動的に公開可能とは判断できません。独自のマッチング判断・出典情報、第三者のメタデータや人手監査内容などは、公開する列を確認した後に配布してください。配布データは、公開する列と利用条件を確認したうえで追加します。
