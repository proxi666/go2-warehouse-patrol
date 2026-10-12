"""Texture-free, non-colliding paint for aisle IDs and Go2 parking."""
from pxr import Gf,UsdGeom
from build_clean_patrol_scene import bind,material

FONT={
 'A':['01110','10001','10001','11111','10001','10001','10001'],
 '1':['00100','01100','00100','00100','00100','00100','01110'],
 '2':['01110','10001','00001','00010','00100','01000','11111'],
 '3':['11110','00001','00001','01110','00001','00001','11110'],
 'G':['01110','10001','10000','10111','10001','10001','01110'],
 'O':['01110','10001','10001','10001','10001','10001','01110'],
 'P':['11110','10001','10001','11110','10000','10000','10000'],
 'R':['11110','10001','10001','11110','10100','10010','10001'],
 'K':['10001','10010','10100','11000','10100','10010','10001'],
 ' ':['00000']*7}

def paint(stage,path,rectangles,mat,z=.005):
 mesh=UsdGeom.Mesh.Define(stage,path);points=[];indices=[]
 for x0,y0,x1,y1 in rectangles:
  start=len(points);points.extend([(x0,y0,z),(x1,y0,z),(x1,y1,z),(x0,y1,z)]);indices.extend(range(start,start+4))
 mesh.CreatePointsAttr(points);mesh.CreateFaceVertexCountsAttr([4]*len(rectangles));mesh.CreateFaceVertexIndicesAttr(indices)
 mesh.CreateNormalsAttr([(0,0,1)]*len(rectangles));mesh.SetNormalsInterpolation('uniform');mesh.CreateSubdivisionSchemeAttr('none')
 mesh.CreateExtentAttr(UsdGeom.Mesh.ComputeExtent(points));bind(mesh.GetPrim(),mat)
 return mesh

def text(stage,path,label,x,y,cell,mat):
 start=x-(len(label)*6-1)*cell/2;rects=[]
 for c,ch in enumerate(label):
  for row,line in enumerate(FONT[ch]):
   for col,value in enumerate(line):
    if value=='1':
     xx=start+(c*6+col)*cell;yy=y+(6-row)*cell;rects.append((xx,yy,xx+cell*.9,yy+cell*.9))
 return paint(stage,path,rects,mat)

def author(stage,config):
 root='/World/PatrolDemo/Markings';UsdGeom.Scope.Define(stage,root)
 yellow=material(stage,'/World/Looks/SafetyYellow',(.95,.7,.04));white=material(stage,'/World/Looks/MarkingWhite',(.9,.9,.9));blue=material(stage,'/World/Looks/ParkBlue',(.04,.2,.48))
 end=config.get('rack_end_y',22.5)
 for index,lane in enumerate(config['aisles'],1):
  x=lane['mouth'][0];group=f'{root}/A{index}';UsdGeom.Xform.Define(stage,group)
  paint(stage,group+'/Edges',[(x-1.43,13,x-1.37,end),(x+1.37,13,x+1.43,end)],yellow)
  text(stage,group+'/Label',f'A{index}',x,13.2,.09,white)
  for y in range(17,int(end),6):
   paint(stage,group+f'/Arrow{y}',[(x-.035,y,x+.035,y+.55),(x-.15,y+.45,x+.15,y+.52)],white)
 x,y,_=config['park'];group=root+'/RobotPark';UsdGeom.Xform.Define(stage,group)
 paint(stage,group+'/Bay',[(x-.75,y-.55,x+.75,y+.55)],blue,z=.004)
 text(stage,group+'/Label','GO2 PARK',x,y-.4,.055,white)
