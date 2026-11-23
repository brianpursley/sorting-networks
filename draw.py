# Copyright (c) 2026 Brian Pursley
# SPDX-License-Identifier: MIT
"""Draw a sorting network from a catalog JSON file and write SVG to stdout."""

import argparse
import json
from pathlib import Path
import sys


def unique_fields(items):
    """Reject JSON objects with repeated field names."""
    fields = {}
    for name, value in items:
        if name in fields:
            raise ValueError(f"duplicate JSON field: {name}")
        fields[name] = value
    return fields


def pack_layers(wire_count, pairs):
    """Put each comparator in the earliest layer available on both wires."""
    next_layer = [0] * wire_count
    layers = []
    for index, pair in enumerate(pairs):
        if not isinstance(pair, list) or len(pair) != 2:
            raise ValueError(f"expected two wire indices at comparator {index}")
        a, b = pair
        if type(a) is not int or type(b) is not int or not 0 <= a < b < wire_count:
            raise ValueError(f"invalid wire pair at comparator {index}: {pair}")
        layer = max(next_layer[a], next_layer[b])
        if layer == len(layers):
            layers.append([])
        layers[layer].append((a, b))
        next_layer[a] = next_layer[b] = layer + 1
    return layers


def position_layer(layer, left):
    """Offset overlapping comparators and return the layer width and their positions."""
    lane_ends = []  # Last wire occupied in each lane, from left to right.
    assignments = []
    for a, b in sorted(layer):
        lane = 0
        while lane < len(lane_ends) and lane_ends[lane] >= a:
            lane += 1
        if lane == len(lane_ends):
            lane_ends.append(b)
        else:
            lane_ends[lane] = b
        assignments.append((lane, a, b))

    lane_spacing = 11
    width = max(32, 16 + lane_spacing * len(lane_ends))
    # Center the lanes within the layer.
    first_x = left + (width - lane_spacing * (len(lane_ends) - 1)) / 2
    return width, [(first_x + lane * lane_spacing, a, b) for lane, a, b in assignments]


def pixel_text(x):
    """Keep half-pixel positions exact and write whole pixels without a decimal point."""
    return str(int(x)) if x.is_integer() else str(x)


def draw(wire_count, layers):
    top, wire_spacing = 94, 15
    bottom = top + wire_spacing * (wire_count - 1)
    left = 49
    bands = []
    for layer in layers:
        band_width, positions = position_layer(layer, left)
        bands.append((left, band_width, positions))
        left += band_width

    width, height = max(320, left + 49), bottom + 40
    title = f'{wire_count}-input sorting network'
    count = sum(len(layer) for layer in layers)
    depth = len(layers)
    count_label = '1 comparator' if count == 1 else f'{count} comparators'
    depth_label = '1 layer' if depth == 1 else f'{depth} layers'
    svg = [
        f'<svg xmlns="http://www.w3.org/2000/svg" role="img" aria-labelledby="title description" '
        f'width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        f'<title id="title">{title}</title>',
        f'<desc id="description">{count_label} in {depth_label}. Wires run left to right, numbered '
        'from zero at the top. Each vertical line compares the wires at its two dots.</desc>',
        f'<rect width="{width}" height="{height}" fill="white"/>',
        '<g font-family="Inter, Arial, sans-serif" fill="#182635">',
        f'<text x="18" y="28" font-size="20" font-weight="600">{title}</text>',
        f'<text x="18" y="50" font-size="14">{count_label} · {depth_label}</text>',
    ]
    for number, (left, band_width, _) in enumerate(bands, 1):
        if number % 2 == 0:
            svg.append(f'<rect x="{left}" y="58" width="{band_width}" height="{height - 67}" fill="#eff4f7"/>')
        label_x = pixel_text(left + band_width / 2)
        for y in (77, bottom + 26):
            svg.append(f'<text x="{label_x}" y="{y}" font-size="12" text-anchor="middle">{number}</text>')
    svg.append('<text x="8" y="77" font-size="11">Layer</text>')

    for wire in range(wire_count):
        y = top + wire_spacing * wire
        svg.append(f'<line x1="36" x2="{width - 36}" y1="{y}" y2="{y}" stroke="#9baab7" stroke-width="0.9"/>')
        for x in (22, width - 22):
            svg.append(f'<text x="{x}" y="{y + 4}" font-size="11" text-anchor="middle">{wire}</text>')

    for number, (_, _, positions) in enumerate(bands, 1):
        svg.append(f'<g id="layer-{number}" fill="#11394c"><title>Layer {number}</title>')
        for x, a, b in positions:
            svg_x = pixel_text(x)
            y1, y2 = top + wire_spacing * a, top + wire_spacing * b
            svg.append(
                f'<g><title>Wires {a} and {b}</title>'
                f'<line x1="{svg_x}" x2="{svg_x}" y1="{y1}" y2="{y2}" stroke="#19536b" stroke-width="1.6"/>'
                f'<circle cx="{svg_x}" cy="{y1}" r="3.1"/><circle cx="{svg_x}" cy="{y2}" r="3.1"/></g>'
            )
        svg.append('</g>')
    svg.extend(['</g>', '</svg>'])
    return '\n'.join(svg) + '\n'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('network', type=Path, help='path to a network JSON file')
    path = parser.parse_args().network
    try:
        network = json.loads(path.read_bytes(), object_pairs_hook=unique_fields)
        if not isinstance(network, dict):
            raise ValueError('expected a network JSON object')
        n, pairs = network.get('N'), network.get('nw')
        if type(n) is not int or n < 1 or not isinstance(pairs, list):
            raise ValueError('expected a positive wire count N and a comparator list nw')
        layers = pack_layers(n, pairs)
        for field, actual in [('L', len(pairs)), ('D', len(layers))]:
            if field in network and (type(network[field]) is not int or network[field] != actual):
                raise ValueError(f'{field} should be {actual}')
    except (OSError, ValueError) as error:
        parser.exit(1, f'{path}: {error}\n')

    sys.stdout.buffer.write(draw(n, layers).encode('utf-8'))


if __name__ == '__main__':
    main()
