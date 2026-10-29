"""Temporal colour styles: single hue, segmented palettes and smooth palettes."""
import numpy as np


def parse_hex(value):
    if not isinstance(value, str) or len(value) != 7 or value[0] != '#':
        raise ValueError('Use colours in #RRGGBB format')
    try:
        return np.array([int(value[i:i+2], 16) for i in (1, 3, 5)], dtype=float) / 255
    except ValueError as exc:
        raise ValueError('Use colours in #RRGGBB format') from exc


def srgb_to_linear(rgb):
    rgb = np.asarray(rgb, dtype=float)
    return np.where(rgb <= .04045, rgb / 12.92, ((rgb + .055) / 1.055) ** 2.4)


def color_at(base, frame, frames, linear=False):
    if not 0 <= frame < frames:
        raise ValueError('Frame outside clip')
    t = frame / max(1, frames-1)
    late = parse_hex(base)
    early = late * .42 + .58
    rgb = early * (1-t) + late * t
    return srgb_to_linear(rgb) if linear else rgb


def style_color(job, modality, frame, frames, *, linear=True, path=False):
    """Whole-clip temporal style; sampling density does not alter a sample's colour."""
    if not 0 <= frame < frames:
        raise ValueError('Frame outside clip')
    t = frame/max(1, frames-1)
    if job.get('time_direction', 'forward') == 'reverse':
        t = 1-t
    t = t**job.get('time_gamma', 1.)
    late = parse_hex(job[f'{modality}_color'])
    start = job.get(f'{modality}_start_color')
    light = job.get('lighten', .8)
    early = parse_hex(start) if start else late*(1-light)+light
    rgb = early*(1-t)+late*t
    palette = job.get(f'{modality}_palette', [])
    if palette:
        colours = np.array([parse_hex(x) for x in palette])
        if job.get('palette_mode','segments') == 'smooth':
            coordinate = t*(len(colours)-1)
            index = min(int(coordinate),len(colours)-1)
            fraction = coordinate-index
            rgb = colours[index]*(1-fraction)+colours[min(index+1,len(colours)-1)]*fraction
        else:
            coordinate = t*len(colours)
            index = min(int(coordinate),len(colours)-1)
            fraction = coordinate-index
            early = colours[index]*(1-light)+light
            rgb = early*(1-fraction)+colours[index]*fraction
    fixed_path = job.get(f'{modality}_path_color') if path else None
    if fixed_path:
        rgb = parse_hex(fixed_path)
    elif not path and frame in job.get('keyframes', []):
        rgb = parse_hex(job.get('keyframe_color', '#555b63'))
    return srgb_to_linear(rgb) if linear else rgb
