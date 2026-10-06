#!/usr/bin/env python3
"""Bounded crops from authored historical field references, never game photos.

The reference image is a creator's reconstruction. Crop receipts preserve the
source URL/hash, crop box, rotation and game/season selection classification.
Studio builds use the checked-in RGBA results and do not download references.
"""
from collections import deque
from PIL import Image
import numpy as np


def remove_grass(image,*,remove_edge_lines=False):
    rgba=np.asarray(image.convert('RGBA')).copy();rgb=rgba[:,:,:3].astype(float)
    grass=(rgb[:,:,1]>100)&(rgb[:,:,1]>rgb[:,:,0]*1.15)&(rgb[:,:,1]>rgb[:,:,2]*1.15)
    rgba[grass,3]=0
    if remove_edge_lines:
        white=rgb.min(axis=2)>220;height,width=white.shape;seen=np.zeros_like(white)
        queue=deque([(0,x)for x in range(width)]+[(height-1,x)for x in range(width)]
            +[(y,0)for y in range(height)]+[(y,width-1)for y in range(height)])
        while queue:
            y,x=queue.popleft()
            if y<0 or y>=height or x<0 or x>=width or seen[y,x] or not white[y,x]:continue
            seen[y,x]=True;queue.extend(((y-1,x),(y+1,x),(y,x-1),(y,x+1)))
        rgba[seen,3]=0
    return Image.fromarray(rgba)


def endzone(image,end,*,bare_turf=False):
    if image.size==(1024,486):box=(28,28,107,458)if end=='N'else(916,28,996,458)
    elif image.size==(1024,625):box=(40,103,118,522)if end=='N'else(906,103,984,522)
    else:raise ValueError('unrecognized historical reference bounds')
    crop=image.crop(box).convert('RGBA')
    if bare_turf:crop=remove_grass(crop)
    return crop.transpose(Image.Transpose.ROTATE_270 if end=='N'else Image.Transpose.ROTATE_90),box


def center(image,box):
    return remove_grass(image.crop(box),remove_edge_lines=True)
