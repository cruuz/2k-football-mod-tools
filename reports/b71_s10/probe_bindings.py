from probe_sequence import preview,p,s,ROOT
# Imports the sequence intentionally, then inspects the final fresh ball-on fixture.
g,c=preview.capture(dict(event='ball on'))
m=c['machine']
try:
 for i in range(6):
  a=0xa959c0+i*112
  print('ELEMENT',i,'names',[m.read_string(m.get(a+j)) for j in (0,4)],'req',m.get(a+64),'slide',m.floats(a+68,1),'binding',m.get(a+96),'material',hex(m.get(a+76)),flush=True)
 print('DRAWS',g['draws'],flush=True)
finally:m.close()
