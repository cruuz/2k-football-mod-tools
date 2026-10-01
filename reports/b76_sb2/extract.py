"""PROVED OFFLINE: extraction recipe used for the SB2 source crops. One decoder, two threads."""
from pathlib import Path
import subprocess
ROOT=Path('/media/noah/Storage/.b76-research/sb')
OUT=ROOT/'sb2/frames'
def main():
 OUT.mkdir(parents=True,exist_ok=True)
 for prefix,name,crop in [('KSc','nfl','1100:240:400:820'),('kv2','espn','736:160:264:546')]:
  source=next((ROOT/'phi_chi_2026-09-28').glob(prefix+'*.mp4'))
  subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-threads','2','-i',str(source),'-an','-vf','fps=1,crop='+crop,'-threads','2','-filter_threads','1',str(OUT/(name+'_%04d.png'))],check=True)
if __name__=='__main__':main()
