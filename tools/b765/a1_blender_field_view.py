"""Offline native-field visualization using Blender's embedded bpy API.

Run with the installed Blender executable, not Studio's Python interpreter::

    blender -b -t 2 --python tools/b765/a1_blender_field_view.py -- scene.json view.png

``bpy`` is provided by Blender itself; this authoring-only helper is not a
Studio provider and adds no pip dependency to Studio's requirements.
"""
import bpy,json,math,sys
from pathlib import Path
args=sys.argv[sys.argv.index('--')+1:];source=Path(args[0]);out=Path(args[1]);doc=json.loads(source.read_text())
bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
materials={}
for name,path in doc['textures'].items():
 mat=bpy.data.materials.new(name);mat.use_nodes=True;n=mat.node_tree.nodes;n.clear();o=n.new('ShaderNodeOutputMaterial');s=n.new('ShaderNodeBsdfPrincipled');s.inputs['Roughness'].default_value=1;t=n.new('ShaderNodeTexImage');t.image=bpy.data.images.load(path);t.interpolation='Linear';t.extension='REPEAT'
 mat.node_tree.links.new(t.outputs['Color'],s.inputs['Base Color']);mat.node_tree.links.new(t.outputs['Alpha'],s.inputs['Alpha']);mat.node_tree.links.new(s.outputs['BSDF'],o.inputs['Surface']);mat.blend_method='BLEND';mat.use_backface_culling=False;materials[name]=mat
for row in doc['meshes']:
 mesh=bpy.data.meshes.new(row['name']);mesh.from_pydata([(z/100,x/100,y/100)for x,y,z in row['positions']],[],row['triangles']);mesh.update();obj=bpy.data.objects.new(row['name'],mesh);bpy.context.collection.objects.link(obj)
 if row['material']in materials:mesh.materials.append(materials[row['material']])
 uv=mesh.uv_layers.new()
 for loop in mesh.loops:
  u,v=row['uv'][loop.vertex_index];uv.data[loop.index].uv=(u,1-v)
bpy.ops.object.camera_add(location=(0,0,130));cam=bpy.context.object;cam.data.type='ORTHO';cam.data.ortho_scale=132;bpy.context.scene.camera=cam
bpy.ops.object.light_add(type='AREA',location=(0,0,100));light=bpy.context.object;light.data.energy=60000;light.data.size=150
scene=bpy.context.scene;scene.render.engine='BLENDER_EEVEE';scene.world.color=(0.5,0.5,0.5);scene.view_settings.view_transform='Standard';scene.view_settings.look='Medium High Contrast';scene.view_settings.exposure=0;scene.view_settings.gamma=1;scene.render.resolution_x=1024;scene.render.resolution_y=512;scene.render.resolution_percentage=100;scene.render.image_settings.file_format='PNG';scene.render.filepath=str(out);bpy.ops.render.render(write_still=True)
