"""Check the two merged APF jobs' authored writes for both pinned profiles."""
import json
from mod_editor.core import apf2k8_situation_mask as masks,apf2k8_fourth_down as fourth
results=[]
policies={f'Book {i}':[[1,2,3] for _ in range(12)] for i in range(masks.MAX_BOOKS)}
for profile in masks.PROFILES:
 a=dict(masks.SituationPatch(profile,masks.encode_data(policies)).words)
 b=dict(fourth.PatchDocument(profile,enabled=True).words)
 abytes={p+i for p in a for i in range(4)};bbytes={p+i for p in b for i in range(4)}
 assert not abytes & bbytes
 assert {**a,**b}=={**b,**a}
 assert not (set(range(masks.DATA_START,masks.DATA_LIMIT))|set(range(masks.CODE_START,masks.CODE_LIMIT))|set(range(masks.RECEIPT_START,masks.RECEIPT_LIMIT))) & bbytes
 results.append(dict(profile=profile.name,situation_words=len(a),fourth_down_words=len(b),byte_writes_disjoint=True,forward_reverse_authored_writes_equal=True,runtime_witnessed=False))
print(json.dumps(results,indent=2))
