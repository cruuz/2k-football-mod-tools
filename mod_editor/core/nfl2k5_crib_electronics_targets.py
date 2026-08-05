"""Retail-free selector catalog for proved Crib electronics surfaces."""

from __future__ import annotations

from typing import Mapping


TARGETS: Mapping[str, tuple[str, int, int]] = {
    "crib_scene_texture:room:22": ("nfl2k5.crib.scene.c0002.t022", 2, 22),
    "crib_scene_texture:room:31": ("nfl2k5.crib.scene.c0002.t031", 2, 31),
    "crib_scene_texture:room:32": ("nfl2k5.crib.scene.c0002.t032", 2, 32),
    "crib_scene_texture:room:39": ("nfl2k5.crib.scene.c0002.t039", 2, 39),
    "crib_scene_texture:room:40": ("nfl2k5.crib.scene.c0002.t040", 2, 40),
    **{
        f"crib_scene_texture:air_hockey:{index}":
        (f"nfl2k5.crib.scene.c0086.t{index:03d}", 86, index)
        for index in range(7)
    },
    **{
        f"crib_scene_texture:dart_machine:{index}":
        (f"nfl2k5.crib.scene.c0090.t{index:03d}", 90, index)
        for index in range(2)
    },
    **{
        f"crib_scene_texture:phone:{index}":
        (f"nfl2k5.crib.scene.c0105.t{index:03d}", 105, index)
        for index in range(5)
    },
    **{
        f"crib_scene_texture:soda_machine:{index}":
        (f"nfl2k5.crib.scene.c0108.t{index:03d}", 108, index)
        for index in range(2)
    },
    "crib_scene_texture:ticker:0": ("nfl2k5.crib.scene.c0111.t000", 111, 0),
    **{
        f"crib_scene_texture:trivia_machine:{index}":
        (f"nfl2k5.crib.scene.c0112.t{index:03d}", 112, index)
        for index in range(3)
    },
}


__all__ = ["TARGETS"]
