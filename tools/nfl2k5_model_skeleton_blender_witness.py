"""Headless Blender edit witness; run with Blender --background --python ... -- IN OUT.

IN must be a user-owned Models body-set export. OUT must be a fresh directory.
This edits bone heads/tails by translation, preserving orientation, then exports
both LODs and head as GLB with custom properties and vertex attributes. It never
includes an input model in the repository. Optional witness, not a game test.
"""
import sys
from pathlib import Path
import shutil
import bpy


def main():
    args = sys.argv[sys.argv.index('--')+1:]
    source,output = (Path(arg).resolve() for arg in args)
    output.mkdir(exist_ok=False)
    print('BLENDER_VERSION',bpy.app.version_string,flush=True)
    for label in ('forearm','thigh'):
        folder=output/label;folder.mkdir()
        shutil.copyfile(source/'player-body-set.skeleton.json',folder/'player-body-set.skeleton.json')
        for file in source.glob('*.gltf'):
            bpy.ops.wm.read_factory_settings(use_empty=True)
            bpy.ops.import_scene.gltf(filepath=str(file))
            if 'body' in file.stem:
                armature=next(o for o in bpy.data.objects if o.type=='ARMATURE')
                bpy.context.view_layer.objects.active=armature;armature.select_set(True)
                bpy.ops.object.mode_set(mode='EDIT')
                bones={b.name.split(':')[-1]:b for b in armature.data.edit_bones}
                snapshots={name:(b.head.copy(),b.tail.copy()) for name,b in bones.items()}
                pivot=snapshots['lelbow' if label=='forearm' else 'lfemur'][0]
                delta=(snapshots['ltibia'][0]-pivot)*.05 if label=='thigh' else None
                for name in (('lwrist','lhand') if label=='forearm' else ('ltibia','lfoot','ltoes')):
                    if name not in bones:
                        continue
                    head,tail=snapshots[name]
                    shift=(head-pivot)*.05 if label=='forearm' else delta
                    bones[name].head=head+shift;bones[name].tail=tail+shift
                bpy.ops.object.mode_set(mode='OBJECT')
            bpy.ops.export_scene.gltf(filepath=str(folder/(file.stem+'.glb')),export_format='GLB',
                                      export_extras=True,export_attributes=True,export_animations=False)
        print('H4_BLENDER_EDIT_EXPORTED',label,flush=True)


if __name__=='__main__':main()
