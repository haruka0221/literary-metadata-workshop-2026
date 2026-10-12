# 2026年10月16日 技術講習会 メタデータ教材（公開前レビュー版）

講習会「文学研究のためのデジタル資料活用：メタデータと本文から何がわかるか」向け。Open Library / Wikidata / OpenAlex の研究用成果物を参加者に説明するための独立した教材です。

## 現時点の状態

本ディレクトリは **公開前レビュー用の実装** です。研究リポジトリへの書き込みは未実施。`data/ol_wikidata_openalex_v1.csv`、`data/workshop_sample.csv` は原データのローカル実行ができるまで **未生成** です。実在しない数値のサンプルCSVは置いていません。

### 教材の範囲

- Historical Open Library targets: 34,789 source Work records（概念的作品34,789とは異なる）
- Project conceptual Work: v7、active 32,066、identity suspended 16、superseded 7
- Wikidata v6: MATCH 8,442 / AMBIGUOUS 358 / NO_MATCH 25,989
- OpenAlex integrated v1: 226,214 operational candidate pairs、7,077 Wに少なくとも1件。数値は確定引用数・固有論文総数ではない。
- OpenAlex v1にはR3+A2候補との7ペア差のQC保留がある。オリジナルv1は改変しない。
- Goodreads / UCSD Book Graphは再配布対象外。

## 作成手順（研究用データを変更しない）

研究リポジトリのcloneに、データの凍結済みファイルがローカルに存在することが前提です。公開前に下記を実行します。

```bash
python workshop-20261016/scripts/build_workshop_data.py --source-root . --schema-only
python workshop-20261016/scripts/build_workshop_data.py --source-root . --output-root workshop-20261016
```

スキーマが予想と違う場合は停止します。実際の列構造を確認し、レビューした修正を新しいスクリプトに反映してください。恣意的なjoinを避けるため、未確認の列名は推測して処理しません。既存CSVが存在したら上書きせず停止します。

## 参加者向けColab

公開後には次の形式のURLをZoomチャットに1つだけ共有します（現在のリンクはまだ有効ではありません）。

`https://colab.research.google.com/github/haruka0221/canon-pipeline/blob/workshop-20261016/workshop-20261016/metadata_workshop.ipynb`

Googleログイン／ランタイムの接続が必要なことがあります。最初のセルでGitHub raw URLのCSVを自動的に読み込みます。ファイルのダウンロード・アップロードは不要です。

## CSV設計

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

元サービスの一般的なCC0方針だけで派生CSVの全項目が自動的に公開可能とは判断できません。独自のマッチング判断・出典情報、第三者のメタデータや人手監査内容などは、公開する列を確認した後に配布してください。GitHubでのブランチ公開前にユーザーが内容をレビューする設計です。
