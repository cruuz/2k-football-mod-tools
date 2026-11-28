import sys; sys.path.insert(0, __import__('os').path.dirname(__import__('os').path.abspath(__file__)))
import numpy as np
from PIL import Image
SAT = 1.2
def saturate(a, factor=SAT):
    a = a.astype(np.float32) / 255.0
    grey = (a[..., :3] @ np.array([0.299, 0.587, 0.114], np.float32))[..., None]
    a[..., :3] = np.clip(grey + (a[..., :3] - grey) * factor, 0, 1)
    return (a * 255 + 0.5).astype(np.uint8)     # as u1_cards.saturate
def box_reduce_f(rgba_u8, f):
    """Premultiplied box reduction -> float premultiplied RGBA 0..1 (colour premultiplied), size/f."""
    a = rgba_u8.astype(np.float64) / 255.0
    pm = a.copy(); pm[..., :3] *= pm[..., 3:4]
    h, w = a.shape[:2]
    return pm.reshape(h // f, f, w // f, f, 4).mean(axis=(1, 3))
def unpremul_u8(r):
    al = r[..., 3:4]
    rgb = np.where(al > 1e-6, r[..., :3] / np.maximum(al, 1e-6), 0.0)
    return (np.concatenate([rgb, al], axis=2) * 255 + 0.5).clip(0, 255).astype(np.uint8)   # as u1_cards.box_reduce
def layer256(path, f=4):
    return box_reduce_f(saturate(np.asarray(Image.open(path).convert('RGBA'))), f)
