#!/usr/bin/env python3
"""Fail-closed, read-only source handling for the 2026-10-16 workshop.
Run from the root of a checkout of canon-pipeline (no source writes).
"""
import argparse, hashlib, json, pathlib
import pandas as pd

SRC = {
 'targets':'derived/identity/openlibrary_analysis_targets_v1.tsv',
 'entities':'derived/identity/source_entities_v3.tsv',
 'map':'derived/identity/work_identity_map_v7.tsv',
 'works':'derived/identity/project_works_v7.tsv',
 'suspensions':'derived/identity/project_work_identity_suspensions_v1.tsv',
 'wikidata':'derived/wikidata_production/full_34789_v6_20260918/final_resolution_v6_34789.tsv',
 'openalex':'derived/openalex_production/integrated_work_visibility_v1/openalex_visibility_by_project_work_v1.tsv',
 'corrections':'derived/identity/openlibrary_target_corrections_v1.tsv',
}
EXPECTED_SHA = {
 'works':'d82fd38c9bf246184798add67e90432616bbab5afaaafcf7c32d74861cb760b5',
 'openalex':'8c3e2e1f55dcff2723dfe2ba60d6ff1d768f4d56456ce009ab65c78e5b740826',
}

def digest(path):
 h=hashlib.sha256()
 with open(path,'rb') as f:
  for b in iter(lambda:f.read(1048576),b''):h.update(b)
 return h.hexdigest()

def read(path):return pd.read_csv(path,sep='\t',dtype=str,keep_default_na=False)

def col(df, options, name):
 hits=[x for x in options if x in df.columns]
 if len(hits)!=1:raise ValueError(f'{name}: expected exactly one of {options}, found {hits}. Actual columns: {list(df.columns)}')
 return hits[0]

def unique(df,key,label):
 if df[key].eq('').any() or df[key].duplicated().any():raise ValueError(f'{label}: missing or duplicate {key}')

def main():
 a=argparse.ArgumentParser();a.add_argument('--source-root',required=True);a.add_argument('--output-root',default='workshop-20261016');a.add_argument('--schema-only',action='store_true');args=a.parse_args()
 root=pathlib.Path(args.source_root).resolve();dest=pathlib.Path(args.output_root).resolve()
 for k,p in SRC.items():
  if not (root/p).is_file():raise FileNotFoundError(root/p)
 for k,v in EXPECTED_SHA.items():
  actual=digest(root/SRC[k]);
  if actual!=v:raise ValueError(f'{k}: source SHA mismatch: {actual} != {v}')
 d={k:read(root/p) for k,p in SRC.items()}
 print(json.dumps({k:{'rows':len(v),'columns':list(v.columns)} for k,v in d.items()},ensure_ascii=False,indent=2))
 if args.schema_only:return
 # The row-spine field must be verified against the actual target file.
 t=d['targets'].copy(); e=d['entities']; m=d['map']; w=d['works']; s=d['suspensions']; wd=d['wikidata'];oa=d['openalex']; fix=d['corrections']
 tid=col(t,['ol_work_id','openlibrary_work_id','current_ol_work_id'],'targets OL ID')
 ttitle=col(t,['title','work_title','ol_title'],'targets title')
 tyear=col(t,['first_publish_year','year','source_first_publish_year'],'targets year')
 # Do not guess authors or edition counts: optional fields stay empty if absent.
 tauthor=next((c for c in ['author_name','primary_author_name','authors'] if c in t),None)
 teditions=next((c for c in ['edition_count','ol_edition_count'] if c in t),None)
 unique(t,tid,'targets');assert len(t)==34789
 unique(e,'entity_id','entities');unique(m,'source_entity_id','map');unique(w,'project_work_id','works')
 unique(oa,'project_work_id','openalex');assert len(w)==32089 and len(oa)==32066 and len(s)==17
 # Exact OL source key from registry; no direct OL ID -> W shortcut.
 ol=e[(e['source']=='openlibrary') & (e['source_namespace']=='work')][['entity_id','source_id']].copy()
 unique(ol,'source_id','OL source registry')
 r=t[[tid,ttitle,tyear]+([tauthor] if tauthor else [])+([teditions] if teditions else [])].copy()
 r=r.rename(columns={tid:'ol_work_id',ttitle:'ol_title',tyear:'ol_first_publish_year'})
 r['ol_author_name']=r[tauthor] if tauthor else ''
 r['ol_edition_count']=r[teditions] if teditions else ''
 r=r[['ol_work_id','ol_title','ol_author_name','ol_first_publish_year','ol_edition_count']]
 # Determine current target ID only from the explicit, frozen corrections list.
 unique(fix,'historical_ol_work_id','corrections');r=r.merge(fix[['historical_ol_work_id','corrected_ol_work_id']],left_on='ol_work_id',right_on='historical_ol_work_id',how='left',validate='one_to_one')
 r['current_ol_work_id']=r['corrected_ol_work_id'].where(r['corrected_ol_work_id'].ne(''),r['ol_work_id'])
 # If targets are already corrected, ensure that using historical as key did not cause silent collisions.
 if r['current_ol_work_id'].duplicated().any():raise ValueError('duplicate corrected/current OL Work ID')
 r=r.drop(columns=['historical_ol_work_id','corrected_ol_work_id'])
 r=r.merge(ol.rename(columns={'source_id':'current_ol_work_id','entity_id':'source_entity_id'}),on='current_ol_work_id',how='left',validate='one_to_one')
 r=r.merge(m[['source_entity_id','project_work_id','membership_role']],on='source_entity_id',how='left',validate='one_to_many')
 if len(r)!=34789:raise ValueError('identity mapping increased row count; inspect multi-membership; no output written')
 r=r.merge(w[['project_work_id','status']].rename(columns={'status':'project_work_status'}),on='project_work_id',how='left',validate='many_to_one')
 r=r.merge(s[['suspended_source_entity_id','project_work_id']].rename(columns={'project_work_id':'suspended_legacy_w'}),left_on='source_entity_id',right_on='suspended_source_entity_id',how='left',validate='many_to_one')
 r['identity_status']='UNRESOLVED_SOURCE'
 r.loc[r['project_work_id'].ne(''),'identity_status']='ACTIVE_MAPPED'
 r.loc[r['suspended_legacy_w'].notna() & r['suspended_legacy_w'].ne(''),'identity_status']='HOLD_OVERAGGREGATED_SOURCE'
 if (r['project_work_status'].fillna('').eq('identity_suspended')).any():raise ValueError('suspended W leaked through active identity map')
 # Wikidata v6 target-key and judgment columns MUST match one of these audited naming variants.
 wk=col(wd,['ol_work_id','openlibrary_work_id','current_ol_work_id'],'Wikidata OL ID')
 wdec=col(wd,['final_decision','decision','resolution_decision','final_resolution'],'Wikidata decision')
 wqid=col(wd,['wikidata_qid','qid','accepted_qid','final_qid'],'Wikidata QID')
 unique(wd,wk,'Wikidata');assert len(wd)==34789
 wd2=wd[[wk,wdec,wqid]].rename(columns={wk:'current_ol_work_id',wdec:'wikidata_decision',wqid:'wikidata_qid'})
 r=r.merge(wd2,on='current_ol_work_id',how='left',validate='one_to_one',indicator='_wd_merge')
 if not r['_wd_merge'].eq('both').all():raise ValueError('Wikidata v6 is not keyed by corrected OL targets; inspect key and regenerate separately')
 r=r.drop(columns='_wd_merge')
 if r['wikidata_decision'].value_counts().to_dict()!={'MATCH':8442,'AMBIGUOUS':358,'NO_MATCH':25989}:raise ValueError('Wikidata decision count mismatch')
 if (r.loc[r['wikidata_decision']!='MATCH','wikidata_qid']!='').any():raise ValueError('Non-MATCH QID populated: review policy')
 req=['project_work_id','measurement_status','total_operational_pairs']
 if not set(req).issubset(oa.columns):raise ValueError(f'OpenAlex columns missing: {set(req)-set(oa.columns)}')
 r=r.merge(oa[req].rename(columns={'measurement_status':'openalex_measurement_status','total_operational_pairs':'openalex_candidate_pairs'}),on='project_work_id',how='left',validate='many_to_one')
 r['openalex_measurement_status']=r['openalex_measurement_status'].fillna('NOT_PROJECT_W_MEASURED')
 r.loc[r['project_work_id'].isna() | r['project_work_id'].eq(''),'openalex_candidate_pairs']=''
 if r.loc[r['identity_status']!='ACTIVE_MAPPED','openalex_candidate_pairs'].fillna('').ne('').any():raise ValueError('OpenAlex data leaked into unresolved or held OL targets')
 if len(r)!=34789 or r['ol_work_id'].duplicated().any():raise ValueError('Row-count/key QC failed')
 r['identity_version']='project_works_v7';r['wikidata_version']='full_34789_v6_20260918';r['openalex_version']='integrated_work_visibility_v1';r['source_commit']='dd8ee20393297edfd786fdb3566291fceccb475c'
 # Edition-count fields absent in OL target file must not be filled from invented API observations.
 dest_data=dest/'data';dest_data.mkdir(parents=True,exist_ok=True)
 full=dest_data/'ol_wikidata_openalex_v1.csv'
 if full.exists():raise FileExistsError(full)
 r.to_csv(full,index=False,encoding='utf-8-sig')
 sample=dest_data/'workshop_sample.csv'
 if sample.exists():raise FileExistsError(sample)
 # Curated broad sample drawn only from historical target set; no fabricated outside-corpus rows.
 titles=r['ol_title'].str.casefold()
 wanted=['news from nowhere','looking backward','erewhon','a crystal age']
 spotlight=r[titles.isin(wanted)]
 others=r[r['identity_status'].eq('ACTIVE_MAPPED') & r['ol_first_publish_year'].str.fullmatch(r'18[7-9][0-9]|1900',na=False)].head(180)
 pd.concat([spotlight,others],ignore_index=True).drop_duplicates('ol_work_id').to_csv(sample,index=False,encoding='utf-8-sig')
 report={'row_count':len(r),'ol_unique':r['ol_work_id'].nunique(),'identity_status':r['identity_status'].value_counts(dropna=False).to_dict(),'wikidata_decision':r['wikidata_decision'].value_counts(dropna=False).to_dict(),'openalex_measurement_status':r['openalex_measurement_status'].value_counts(dropna=False).to_dict(),'input_sha256':{k:digest(root/p) for k,p in SRC.items()},'output_sha256':{x.name:digest(x) for x in [full,sample]}}
 (dest_data/'qc_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 print(json.dumps(report,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
