import pathlib,shlex,subprocess,sys
root=pathlib.Path.cwd(); g=[str(root/'.scratch/g')]
message,other=sys.argv[1:]
def run(*args,input=None):
    cmd=g+list(args);print('+ '+shlex.join(cmd),flush=True)
    return subprocess.check_output(cmd,input=input,text=True).strip()
head=run('rev-parse','HEAD');parent=run('rev-parse',other)
paths=sorted(set(run('diff','--name-only','HEAD').splitlines())|set(run('diff','--cached','--name-only').splitlines()))
assert paths and all(not p.startswith('.scratch/') for p in paths)
run('add','--',*paths)
assert not run('ls-files','--unmerged')
assert set(run('diff','--cached','--name-only').splitlines())==set(paths)
tree=run('write-tree');sha=run('commit-tree',tree,'-p',head,'-p',parent,input=message+'\n')
run('update-ref','refs/heads/astra/b71-a5-scorebug-integrate',sha,head)
for file in ['MERGE_HEAD','MERGE_MSG','MERGE_MODE','AUTO_MERGE']:
    (root/'.scratch/private.git'/file).unlink(missing_ok=True)
print('MERGE_COMMIT',sha)
print('EXPLICIT_PATHS',*paths,sep='\n')
