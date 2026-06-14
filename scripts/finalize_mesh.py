import struct, numpy as np, sys
from collections import defaultdict, Counter, deque
P=sys.argv[1]
f=open(P,'rb'); f.read(80); n=struct.unpack('<I',f.read(4))[0]
raw=[]
for _ in range(n):
    d=struct.unpack('<12fH',f.read(50)); raw.append(np.array(d[3:12]).reshape(3,3))
# weld coincident vertices
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

# --- coherent orientation (BFS over shared edges) ---
def reorient(F):
    F=[tuple(t) for t in F]
    em=defaultdict(list)
    for fi,(a,b,c) in enumerate(F):
        for (u,v) in ((a,b),(b,c),(c,a)): em[(min(u,v),max(u,v))].append(fi)
    flip=[False]*len(F); done=[False]*len(F)
    def dirs(fi):
        a,b,c=F[fi]; e=[(a,b),(b,c),(c,a)]
        return [(v,u) for (u,v) in e] if flip[fi] else e
    for s in range(len(F)):
        if done[s]: continue
        done[s]=True; q=deque([s])
        while q:
            fi=q.popleft()
            for (u,v) in dirs(fi):
                for gj in em[(min(u,v),max(u,v))]:
                    if gj==fi or done[gj]: continue
                    gd=dirs(gj)
                    # if neighbour already traverses (u,v) the same way, flip it
                    if (u,v) in gd: flip[gj]=True
                    done[gj]=True; q.append(gj)
    return [F[i][::-1] if flip[i] else F[i] for i in range(len(F))]

faces=reorient(faces)

# --- fill holes using directed boundary half-edges (robust at bowtie/figure-8 vertices) ---
# Boundary half-edges form the hole loops. At a vertex shared by two holes a greedy "next"
# pick wanders and fans a huge overlapping triangle; instead choose the next edge by turning
# angle (hug the boundary), which traces each SIMPLE cycle correctly even through shared verts.
import math
def fill_holes(F,PA):
    D=set(); uec=Counter()
    for a,b,c in F:
        for (u,v) in ((a,b),(b,c),(c,a)): D.add((u,v)); uec[(min(u,v),max(u,v))]+=1
    # genuine gaps are UNDIRECTED edges used once (orientation may be locally inconsistent, so
    # don't trust directed-only tests, which would flag legit shared edges and over-fill)
    bhe=[(u,v) for (u,v) in D if uec[(min(u,v),max(u,v))]==1]
    out=defaultdict(list)
    for (u,v) in bhe: out[u].append(v)
    def turn(u,v,w):                                # ccw angle at v from (v->u) to (v->w)
        a=math.atan2(PA[u][1]-PA[v][1], PA[u][0]-PA[v][0])
        b=math.atan2(PA[w][1]-PA[v][1], PA[w][0]-PA[v][0])
        d=b-a
        while d<=0: d+=2*math.pi
        while d>2*math.pi: d-=2*math.pi
        return d
    usedh=set(); newf=[]
    for (su,sv) in bhe:
        if (su,sv) in usedh: continue
        loop=[su]; cu,cv=su,sv
        for _ in range(100000):
            usedh.add((cu,cv)); loop.append(cv)
            if cv==su: break
            cands=[w for w in out[cv] if (cv,w) not in usedh]
            if not cands: break
            nw=min(cands, key=lambda w: turn(cu,cv,w))   # smallest left turn hugs the hole
            cu,cv=cv,nw
        if len(loop)>=4 and loop[0]==loop[-1]:
            vs=loop[:-1]
            # fill opposite to the boundary direction so winding stays outward-consistent
            for k in range(1,len(vs)-1): newf.append((vs[0],vs[k+1],vs[k]))
    return F+newf

PA=np.array(pts)
prev=-1
for _ in range(6):                                   # iterate: fans can expose nested gaps
    faces=fill_holes(faces,PA)
    ue=Counter()
    for a,b,c in faces:
        for u,v in ((a,b),(b,c),(c,a)): ue[(min(u,v),max(u,v))]+=1
    nb=sum(1 for c in ue.values() if c!=2)
    if nb==prev or nb==0: break
    prev=nb
    faces=reorient(faces)

faces=reorient(faces)
PA=np.array(pts); Fo=np.array(faces)
vol=sum(np.dot(PA[a],np.cross(PA[b],PA[c])) for a,b,c in Fo)/6.0
if vol<0: Fo=Fo[:,[0,2,1]]
def nrm(a,b,c):
    u=b-a;v=c-a;nn=np.cross(u,v);L=np.linalg.norm(nn) or 1.0;return nn/L
with open(P,'wb') as fo:
    fo.write(b'\0'*80); fo.write(struct.pack('<I',len(Fo)))
    for a,b,c in Fo:
        A,B,C=PA[a],PA[b],PA[c]; fo.write(struct.pack('<12fH',*nrm(A,B,C),*A,*B,*C,0))
print('finalized tris',len(Fo),'(filled, oriented, vol %.0f)'%vol)
