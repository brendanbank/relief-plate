import struct, numpy as np, sys
from collections import defaultdict, Counter, deque
P=sys.argv[1]
f=open(P,'rb'); f.read(80); n=struct.unpack('<I',f.read(4))[0]
raw=[]
for _ in range(n):
    d=struct.unpack('<12fH',f.read(50)); raw.append(np.array(d[3:12]).reshape(3,3))
# weld
key={}; pts=[]
def vid(p):
    k=tuple(np.round(p,3))
    if k not in key: key[k]=len(pts); pts.append(np.array(k,float))
    return key[k]
faces=[]
for t in raw:
    a,b,c=vid(t[0]),vid(t[1]),vid(t[2])
    if a!=b and b!=c and a!=c: faces.append((a,b,c))
# remove coincident duplicate faces: keep count%2 copies per unsorted-key
cnt=Counter(tuple(sorted(t)) for t in faces)
keepN={k:v%2 for k,v in cnt.items()}; seen=Counter(); ded=[]
for t in faces:
    k=tuple(sorted(t))
    if seen[k]<keepN[k]: ded.append(t); seen[k]+=1
faces=ded
# fill boundary (undirected count==1) loops by fan
ue=Counter()
for a,b,c in faces:
    for u,v in ((a,b),(b,c),(c,a)): ue[(min(u,v),max(u,v))]+=1
bnd=[e for e,c in ue.items() if c==1]
adj=defaultdict(list)
for u,v in bnd: adj[u].append(v); adj[v].append(u)
used=set()
def uk(a,b): return (min(a,b),max(a,b))
for s in list(adj.keys()):
    for st in adj[s]:
        if uk(s,st) in used: continue
        loop=[s]; used.add(uk(s,st)); cur=st; prev=s; g=0
        while cur!=s and g<100000:
            g+=1; loop.append(cur); nx=None
            for w in adj[cur]:
                if uk(cur,w) not in used: nx=w; break
            if nx is None: break
            used.add(uk(cur,nx)); prev=cur; cur=nx
        if len(loop)>=3:
            for k in range(1,len(loop)-1): faces.append((loop[0],loop[k],loop[k+1]))
# coherent orientation via BFS
em=defaultdict(list)
F=np.array(faces)
for fi,(a,b,c) in enumerate(F):
    for i,(u,v) in enumerate(((a,b),(b,c),(c,a))): em[(min(u,v),max(u,v))].append((fi,i))
oriented=np.zeros(len(F),bool); flip=np.zeros(len(F),bool)
for s in range(len(F)):
    if oriented[s]: continue
    oriented[s]=True; q=deque([s])
    while q:
        fi=q.popleft(); t=F[fi]
        for i in range(3):
            u,v=t[i],t[(i+1)%3]
            cu,cv=(v,u) if flip[fi] else (u,v)
            for gj,gi in em[(min(u,v),max(u,v))]:
                if gj==fi or oriented[gj]: continue
                gt=F[gj]; gu,gv=gt[gi],gt[(gi+1)%3]
                if (gu,gv)==(cu,cv): flip[gj]=True
                oriented[gj]=True; q.append(gj)
Fo=np.where(flip[:,None],F[:,[0,2,1]],F)
PA=np.array(pts)
vol=sum(np.dot(PA[a],np.cross(PA[b],PA[c])) for a,b,c in Fo)/6.0
if vol<0: Fo=Fo[:,[0,2,1]]
def nrm(a,b,c):
    u=b-a;v=c-a;nn=np.cross(u,v);L=np.linalg.norm(nn) or 1.0;return nn/L
with open(P,'wb') as fo:
    fo.write(b'\0'*80); fo.write(struct.pack('<I',len(Fo)))
    for a,b,c in Fo:
        A,B,C=PA[a],PA[b],PA[c]; fo.write(struct.pack('<12fH',*nrm(A,B,C),*A,*B,*C,0))
print('finalized tris',len(Fo),'removed dup-pairs, filled, oriented (vol %.0f)'%vol)
