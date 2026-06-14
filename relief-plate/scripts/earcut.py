# Faithful minimal port of mapbox/earcut (no z-curve hashing). Robust hole handling.
import math
class Node:
    __slots__=('i','x','y','prev','next','steiner')
    def __init__(self,i,x,y):
        self.i=i;self.x=x;self.y=y;self.prev=None;self.next=None;self.steiner=False
def earcut(data, hole_indices=None, dim=2):
    has_holes = bool(hole_indices)
    outer_len = hole_indices[0]*dim if has_holes else len(data)
    outer = linked_list(data,0,outer_len,dim,True)
    triangles=[]
    if outer is None or outer.next is outer.prev: return triangles
    if has_holes: outer = eliminate_holes(data,hole_indices,outer,dim)
    earcut_linked(outer,triangles,dim)
    return triangles
def linked_list(data,start,end,dim,clockwise):
    last=None
    if clockwise == (signed_area(data,start,end,dim)>0):
        for i in range(start,end,dim): last=insert_node(i//dim,data[i],data[i+1],last)
    else:
        for i in range(end-dim,start-1,-dim): last=insert_node(i//dim,data[i],data[i+1],last)
    if last and equals(last,last.next):
        remove_node(last); last=last.next
    return last
def filter_points(start,end=None):
    if start is None: return start
    if end is None: end=start
    p=start; again=True
    while again or p is not end:
        again=False
        if not p.steiner and (equals(p,p.next) or area(p.prev,p,p.next)==0):
            remove_node(p); p=end=p.prev
            if p is p.next: break
            again=True
        else:
            p=p.next
    return end
def earcut_linked(ear,triangles,dim,pas=0):
    if ear is None: return
    ear=filter_points(ear)
    stop=ear; prev=None; nxt=None
    while ear.prev is not ear.next:
        prev=ear.prev; nxt=ear.next
        if is_ear(ear):
            triangles.append(prev.i); triangles.append(ear.i); triangles.append(nxt.i)
            remove_node(ear); ear=nxt.next; stop=nxt.next; continue
        ear=nxt
        if ear is stop:
            if pas==0: earcut_linked(filter_points(ear),triangles,dim,1)
            elif pas==1:
                ear=cure_local_intersections(filter_points(ear),triangles); earcut_linked(ear,triangles,dim,2)
            elif pas==2: split_earcut(ear,triangles,dim)
            break
def is_ear(ear):
    a=ear.prev;b=ear;c=ear.next
    if area(a,b,c)>=0: return False
    p=ear.next.next
    while p is not ear.prev:
        if point_in_triangle(a.x,a.y,b.x,b.y,c.x,c.y,p.x,p.y) and area(p.prev,p,p.next)>=0:
            return False
        p=p.next
    return True
def cure_local_intersections(start,triangles):
    p=start
    while True:
        a=p.prev;b=p.next.next
        if not equals(a,b) and intersects(a,p,p.next,b) and locally_inside(a,b) and locally_inside(b,a):
            triangles.append(a.i);triangles.append(p.i);triangles.append(b.i)
            remove_node(p);remove_node(p.next); p=start=b
        p=p.next
        if p is start: break
    return filter_points(p)
def split_earcut(start,triangles,dim):
    a=start
    while True:
        b=a.next.next
        while b is not a.prev:
            if a.i!=b.i and is_valid_diagonal(a,b):
                c=split_polygon(a,b)
                a=filter_points(a,a.next); c=filter_points(c,c.next)
                earcut_linked(a,triangles,dim); earcut_linked(c,triangles,dim); return
            b=b.next
        a=a.next
        if a is start: break
def eliminate_holes(data,hole_indices,outer,dim):
    queue=[]
    n=len(hole_indices)
    for i in range(n):
        start=hole_indices[i]*dim
        end=hole_indices[i+1]*dim if i<n-1 else len(data)
        lst=linked_list(data,start,end,dim,False)
        if lst is lst.next: lst.steiner=True
        queue.append(get_leftmost(lst))
    queue.sort(key=lambda nd:nd.x)
    for hole in queue:
        outer=eliminate_hole(hole,outer)
    return outer
def eliminate_hole(hole,outer):
    bridge=find_hole_bridge(hole,outer)
    if bridge is None:
        return outer
    bridge_reverse=split_polygon(bridge,hole)
    filter_points(bridge_reverse,bridge_reverse.next)
    return filter_points(bridge,bridge.next)
def find_hole_bridge(hole,outer):
    p=outer; hx=hole.x; hy=hole.y; qx=-math.inf; m=None
    while True:
        if hy<=p.y and hy>=p.next.y and p.next.y!=p.y:
            x=p.x+(hy-p.y)*(p.next.x-p.x)/(p.next.y-p.y)
            if x<=hx and x>qx:
                qx=x; m=p if p.x<p.next.x else p.next
                if x==hx:
                    return m
        p=p.next
        if p is outer: break
    if m is None: return None
    stop=m; mx=m.x; my=m.y; tan_min=math.inf
    p=m
    while True:
        if hx>=p.x>=mx and hx!=p.x and point_in_triangle(hy<my and hx or qx, hy, mx,my,hx<mx and hx or qx, hy, p.x,p.y):
            pass
        p=p.next
        if p is stop: break
    # robust version of the above loop:
    p=m; tan_min=math.inf; m_best=m
    while True:
        if (hx>=p.x>=mx) and (hx!=p.x) and point_in_triangle(hy<my and hx or qx,hy,mx,my,hy<my and qx or hx,hy,p.x,p.y):
            tan=abs(hy-p.y)/(hx-p.x) if (hx-p.x)!=0 else math.inf
            if locally_inside(p,hole) and (tan<tan_min or (tan==tan_min and (p.x>m_best.x or (p.x==m_best.x and sector_contains(m_best,p))))):
                m_best=p; tan_min=tan
        p=p.next
        if p is stop: break
    return m_best
def sector_contains(m,p):
    return area(m.prev,m,p.prev)<0 and area(p.next,m,m.next)<0
def get_leftmost(start):
    p=start; leftmost=start
    while True:
        if p.x<leftmost.x or (p.x==leftmost.x and p.y<leftmost.y): leftmost=p
        p=p.next
        if p is start: break
    return leftmost
def is_valid_diagonal(a,b):
    return (a.next.i!=b.i and a.prev.i!=b.i and not intersects_polygon(a,b)
            and ((locally_inside(a,b) and locally_inside(b,a) and middle_inside(a,b)
                  and (area(a.prev,a,b.prev) or area(a,b.prev,b))) or
                 (equals(a,b) and area(a.prev,a,a.next)>0 and area(b.prev,b,b.next)>0)))
def area(p,q,r): return (q.y-p.y)*(r.x-q.x)-(q.x-p.x)*(r.y-q.y)
def equals(p1,p2): return p1.x==p2.x and p1.y==p2.y
def intersects(p1,q1,p2,q2):
    o1=sign(area(p1,q1,p2));o2=sign(area(p1,q1,q2));o3=sign(area(p2,q2,p1));o4=sign(area(p2,q2,q1))
    if o1!=o2 and o3!=o4: return True
    if o1==0 and on_segment(p1,p2,q1): return True
    if o2==0 and on_segment(p1,q2,q1): return True
    if o3==0 and on_segment(p2,p1,q2): return True
    if o4==0 and on_segment(p2,q1,q2): return True
    return False
def on_segment(p,q,r): return min(p.x,r.x)<=q.x<=max(p.x,r.x) and min(p.y,r.y)<=q.y<=max(p.y,r.y)
def sign(n): return (n>0)-(n<0)
def intersects_polygon(a,b):
    p=a
    while True:
        if p.i!=a.i and p.next.i!=a.i and p.i!=b.i and p.next.i!=b.i and intersects(p,p.next,a,b):
            return True
        p=p.next
        if p is a: break
    return False
def locally_inside(a,b):
    if area(a.prev,a,a.next)<0:
        return area(a,b,a.next)>=0 and area(a,a.prev,b)>=0
    return area(a,b,a.prev)<0 or area(a,a.next,b)<0
def middle_inside(a,b):
    p=a; inside=False; px=(a.x+b.x)/2; py=(a.y+b.y)/2
    while True:
        if ((p.y>py)!=(p.next.y>py)) and p.next.y!=p.y and (px<(p.next.x-p.x)*(py-p.y)/(p.next.y-p.y)+p.x):
            inside=not inside
        p=p.next
        if p is a: break
    return inside
def split_polygon(a,b):
    a2=Node(a.i,a.x,a.y);b2=Node(b.i,b.x,b.y);an=a.next;bp=b.prev
    a.next=b;b.prev=a;a2.next=an;an.prev=a2;b2.next=a2;a2.prev=b2;bp.next=b2;b2.prev=bp
    return b2
def insert_node(i,x,y,last):
    p=Node(i,x,y)
    if last is None: p.prev=p;p.next=p
    else: p.next=last.next;p.prev=last;last.next.prev=p;last.next=p
    return p
def remove_node(p):
    p.next.prev=p.prev;p.prev.next=p.next
def point_in_triangle(ax,ay,bx,by,cx,cy,px,py):
    return ((cx-px)*(ay-py)-(ax-px)*(cy-py)>=0 and
            (ax-px)*(by-py)-(bx-px)*(ay-py)>=0 and
            (bx-px)*(cy-py)-(cx-px)*(by-py)>=0)
def signed_area(data,start,end,dim):
    s=0.0;j=end-dim
    for i in range(start,end,dim):
        s+=(data[j]-data[i])*(data[i+1]+data[j+1]);j=i
    return s
