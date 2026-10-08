#!/usr/bin/env python3
"""Frozen V2-21 model scorer, no removed target layers or reference labels.

Uses the original unchanged prepare() and score_fold() science functions,
with portable input/output handling and strict authoritative GEOID checks.
"""
from __future__ import annotations
import argparse, hashlib, json, importlib.util
from pathlib import Path
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parent
MODEL=ROOT/'src/v2_21_frozen_model.py'
REGIONS=('eastern-ok','eastern-wa','maricopa-az','northern-ca','south-central-tx')
COUNTS={'eastern-ok':1192,'eastern-wa':415,'maricopa-az':1593,'northern-ca':591,'south-central-tx':6003}
FOUR_PRIMARY=('eastern-ok','maricopa-az','northern-ca','south-central-tx')
FEATURE_FROZEN_SHA='0C92ED6B38A5AD78F6406569765FB87AC311D93121D278ACD0AE6B51DBFE90A6'
SUBMISSION_FROZEN_SHA='D6DC4E8DD6C3D94D156049AC2364E289C38EE38E46BF3C1E37107F8F4E0C7C57'
COMPONENTS=('model_building','model_poi_base','model_poi_head','model_poi_alpha50','model_road','v2_21_mean')

def digest(p:Path):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for part in iter(lambda:f.read(1<<20),b''):h.update(part)
 return h.hexdigest().upper()

def guard(ok,msg):
 if not ok:raise RuntimeError(msg)

def load_model():
 spec=importlib.util.spec_from_file_location('v2_21_frozen_model',MODEL)
 guard(spec is not None and spec.loader is not None,'MISSING_OR_INVALID_FROZEN_MODEL')
 mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
 return mod

def main():
 ap=argparse.ArgumentParser(description='Reference-free V2-21 Overture-only scoring from derived features')
 ap.add_argument('--features',type=Path,default=ROOT/'outputs/V2-2-overture-core-features.csv')
 ap.add_argument('--samples',type=Path,default=ROOT/'inputs/sample')
 ap.add_argument('--output-dir',type=Path,required=True,help='Must be new / absent; never overwrite frozen inputs')
 ap.add_argument('--compare-upload',type=Path,help='Optional downloaded original Zindi CSV (not required to score)')
 ap.add_argument('--strict-frozen-feature-hash',action='store_true',help='Require byte-identical frozen features, not just compatible data')
 args=ap.parse_args()
 features=args.features.resolve(); samples=args.samples.resolve(); out=args.output_dir.resolve()
 guard(features.is_file(),'MISSING_FEATURE_TABLE');guard(samples.is_dir(),'MISSING_SAMPLE_DIRECTORY')
 guard(not out.exists(),'OUTPUT_DIR_ALREADY_EXISTS_CHOOSE_FRESH')
 guard(out!=ROOT and out not in [features,samples],'UNSAFE_OUTPUT_LOCATION')
 found_feature_hash=digest(features)
 if args.strict_frozen_feature_hash:guard(found_feature_hash==FEATURE_FROZEN_SHA,'FROZEN_FEATURE_BYTES_DIFFER')
 model=load_model()
 df=pd.read_csv(features,dtype={'GEOID':'string','region':'string'})
 guard(list(df.columns[:2])==['region','GEOID'],'FEATURE_ID_COLUMNS_MISMATCH')
 guard(len(df)==9794 and df.GEOID.notna().all() and bool(df.GEOID.is_unique),'FEATURE_GEOID_MEMBERSHIP_FAIL')
 guard(df.region.value_counts().to_dict()==COUNTS,'FEATURE_REGION_COUNTS_FAIL')
 # Never read any sample placeholder gap values as training labels.
 prepared=model.prepare(df)
 for c in COMPONENTS:prepared[c]=np.nan
 for hold in REGIONS:
  tr=prepared[prepared.region.ne(hold)].copy();te=prepared[prepared.region.eq(hold)].copy()
  scores=model.score_fold(tr,te)
  for col,key in [('model_building','building'),('model_poi_base','poi_base'),('model_poi_head','poi_head'),('model_poi_alpha50','poi_alpha50'),('model_road','road'),('v2_21_mean','mean')]:
   prepared.loc[te.index,col]=scores[key]
 a=prepared[list(COMPONENTS)].to_numpy(dtype=float)
 guard(bool(np.isfinite(a).all()),'NONFINITE_MODEL_RESULT')
 guard(bool(((a>=0)&(a<=1)).all()),'OUT_OF_RANGE_MODEL_RESULT')
 frames=[];seen=set()
 for reg in REGIONS:
  sample=samples/(reg+'-sample-submission.csv')
  guard(sample.is_file(),'MISSING_PUBLIC_SAMPLE:'+reg)
  s=pd.read_csv(sample,dtype='string')
  guard(list(s.columns)==['GEOID','transport_gap','building_gap','poi_gap','coverage_gap_score'],'SAMPLE_SCHEMA:'+reg)
  ids=s.GEOID.tolist()
  guard(len(ids)==COUNTS[reg] and all(isinstance(i,str) and len(i)==11 and i.isdecimal() for i in ids),'INVALID_SAMPLE_GEOID:'+reg)
  guard(len(ids)==len(set(ids)) and not(set(ids)&seen),'DUPLICATE_SAMPLE_GEOID:'+reg)
  seen.update(ids)
  pred=prepared[prepared.region.eq(reg)].set_index('GEOID')['v2_21_mean']
  guard(set(ids)==set(pred.index),'SAMPLE_MODEL_MEMBERSHIP_DIFFERENCE:'+reg)
  frames.append(pd.DataFrame({'GEOID':pd.Series(ids,dtype='string'),'coverage_gap_score':pred.reindex(ids).to_numpy(dtype=float)}))
 combined=pd.concat(frames,ignore_index=True)
 guard(len(combined)==9794 and len(seen)==9794,'FINAL_SUBMISSION_MEMBERSHIP_FAIL')
 guard(sum(COUNTS[x] for x in FOUR_PRIMARY)==9379,'FOUR_PRIMARY_COUNT_MISMATCH')
 # Do not claim the submitted Eastern Washington rows were evaluated in public RMSE.
 out.mkdir(parents=True,exist_ok=False)
 candidate=out/'candidate-components.csv';final=out/'submission.csv'
 prepared[['region','GEOID',*COMPONENTS]].to_csv(candidate,index=False)
 combined.to_csv(final,index=False,lineterminator='\n',float_format='%.15g')
 check=pd.read_csv(final,dtype={'GEOID':'string'})
 guard(check.GEOID.tolist()==combined.GEOID.tolist(),'FINAL_SERIALIZED_GEOID_ORDER_DRIFT')
 err=float(np.max(np.abs(check.coverage_gap_score.to_numpy(dtype=float)-combined.coverage_gap_score.to_numpy(dtype=float))))
 guard(err<1e-12,'FINAL_SERIALIZATION_NUMERIC_DRIFT')
 report={'status':'PASS_REFERENCE_FREE_SCORER','version':'DOC_P6_PUBLIC_SCORER_v1.0','method':'frozen_original_v2_21_prepare_and_score_fold','feature_sha256':found_feature_hash,'frozen_features_sha256':FEATURE_FROZEN_SHA,'frozen_feature_byte_identity':found_feature_hash==FEATURE_FROZEN_SHA,'submitted_sha256_reference':SUBMISSION_FROZEN_SHA,'generated_sha256':digest(final),'generated_byte_identical_to_original':digest(final)==SUBMISSION_FROZEN_SHA,'row_count':9794,'four_primary_scored_region_rows':9379,'supplemental_eastern_wa_rows':415,'serialized_max_abs_delta':err,'model_changes':'NONE','forbidden_target_inputs_used':False}
 if args.compare_upload:
  old=pd.read_csv(args.compare_upload,dtype={'GEOID':'string'})
  guard(list(old.columns)==['GEOID','coverage_gap_score'] and len(old)==9794 and old.GEOID.tolist()==combined.GEOID.tolist(),'UPLOADED_CSV_GEOID_OR_SCHEMA_DRIFT')
  delta=float(np.max(np.abs(old.coverage_gap_score.to_numpy(dtype=float)-combined.coverage_gap_score.to_numpy(dtype=float))))
  report['original_upload_sha256']=digest(args.compare_upload)
  report['compare_upload_max_abs_delta']=delta
  guard(delta<=1e-10,'FINAL_SUBMISSION_NUMERICAL_MISMATCH')
 (out/'REPORT.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf8')
 print('DOC_P6_PUBLIC_SCORER=PASS')
 print('ROWS=9794 FOUR_PRIMARY_ROWS=9379 FIFTH_SUPPLEMENT=415')
 print('OUTPUT='+str(final));print('REPORT='+str(out/'REPORT.json'))
 if args.compare_upload:print(f'UPLOAD_MAX_ABS_SCORE_DELTA={report["compare_upload_max_abs_delta"]:.15g}')
if __name__=='__main__':
 try:main()
 except Exception as e:
  import sys
  print('DOC_P6_PUBLIC_SCORER=FAIL '+type(e).__name__+': '+str(e),file=sys.stderr)
  sys.exit(1)
