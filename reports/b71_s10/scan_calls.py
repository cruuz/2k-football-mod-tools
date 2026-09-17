from scan_writers import im,cs
for s in im.sections:
 if s.executable:
  for va,size,mn,op in cs.disasm_lite(im.read(s.start,s.raw_size),s.start):
   if op in ('0xfc330','0xfc340','0xfc700','0xfc720') and mn in ('call','jmp'):print('CALLER',hex(va),mn,op,flush=True)
