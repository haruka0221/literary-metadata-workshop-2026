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
GitHub上には主に再現用スクリプト、テスト、仕様書を公開しています。

Edition件数はOpen Libraryに登録された書誌レコードの観測値であり、
実際の出版部数や出版履歴の完全な記録ではありません。

## 公開状況

このリポジトリでは、講習会用のコード・テスト・仕様書を公開しています。

- Open Library Editionの抽出・集計：検証済み
- Wikidata・OpenAlexとの統合プレビューv4：ローカル生成・検証済み
- 参加者向けCSV：整備中（GitHubでは未公開）
- Colabノートブック：配布データとの接続・動作確認は未完了

研究用リポジトリのデータや凍結済み成果物は変更していません。

### 教材の範囲

- Historical Open Library targets: 34,789 source Work records（概念的作品34,789とは異なる）
- Project conceptual Work: v7、active 32,066、identity suspended 16、superseded 7
- Wikidata v6: MATCH 8,442 / AMBIGUOUS 358 / NO_MATCH 25,989
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

参加者向けCSVの取得・利用手順は、公開準備が整い次第追記します。

## 参加者向けColab

ノートブックは以下から開けますが、講習会用データの読み込みを含む動作確認はまだ完了していません。

`https://colab.research.google.com/github/haruka0221/literary-metadata-workshop-2026/blob/main/metadata_workshop.ipynb`

Googleログイン／ランタイムの接続が必要なことがあります。CSVの読み込み先と実習手順は、配布用データの公開後に検証します。

## 配布予定CSVの設計

`ol_wikidata_openalex_v1.csv`: 一行= historical Open Library analysis target。主な列は `ol_work_id`, `current_ol_work_id`, `ol_title`, `ol_author_name`, `ol_first_publish_year`, `ol_edition_count`, `source_entity_id`, `project_work_id`, `identity_status`, `wikidata_decision`, `wikidata_qid`, `openalex_candidate_pairs`, `openalex_measurement_status`, `identity_version`, `wikidata_version`, `openalex_version`, `source_commit`。

`workshop_sample.csv`: 同じスキーマで、現行の歴史的集合から選んだ講習会向け部分標本。Butler *Erewhon* (1872) など歴史的対象の期間外の作品は、この標本に存在しない可能性があります。別途取得するなら`outside_corpus`と出典を別表で明示してください。

`data_dictionary.csv`: カラムの簡易説明。`qc_report.json`: 実際のファイルを生成できた場合に出力する件数・SHA256・判定数。

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
