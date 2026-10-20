"""Animal silhouette definitions for avatar generation.

Each animal is defined as a list of shape tuples:
  ("circle", cx, cy, r)
  ("ellipse", cx, cy, rx, ry)
  ("polygon", [(x1,y1), (x2,y2), ...])

Coordinates are normalized 0-1 (scaled to image size at render time).
"""

from typing import Literal

Point = tuple[float, float]
Circle = tuple[Literal["circle"], float, float, float]  # cx, cy, r
Ellipse = tuple[Literal["ellipse"], float, float, float, float]  # cx, cy, rx, ry
Polygon = tuple[Literal["polygon"], list[Point]]
Shape = Circle | Ellipse | Polygon
AnimalDef = list[Shape]

ANIMALS: list[tuple[str, AnimalDef]] = [
    (
        "cat",
        [
            ("ellipse", 0.5, 0.55, 0.25, 0.3),  # body
            ("circle", 0.5, 0.3, 0.15),  # head
            ("polygon", [(0.38, 0.3), (0.35, 0.15), (0.42, 0.22)]),  # left ear
            ("polygon", [(0.62, 0.3), (0.65, 0.15), (0.58, 0.22)]),  # right ear
            ("ellipse", 0.35, 0.78, 0.05, 0.12),  # left leg
            ("ellipse", 0.65, 0.78, 0.05, 0.12),  # right leg
            ("ellipse", 0.75, 0.6, 0.12, 0.03),  # tail
        ],
    ),
    (
        "dog",
        [
            ("ellipse", 0.5, 0.55, 0.28, 0.25),  # body
            ("circle", 0.5, 0.3, 0.16),  # head
            ("ellipse", 0.36, 0.22, 0.06, 0.1),  # left ear (floppy)
            ("ellipse", 0.64, 0.22, 0.06, 0.1),  # right ear (floppy)
            ("ellipse", 0.5, 0.38, 0.06, 0.04),  # snout
            ("ellipse", 0.35, 0.78, 0.05, 0.12),  # left leg
            ("ellipse", 0.65, 0.78, 0.05, 0.12),  # right leg
            ("ellipse", 0.78, 0.45, 0.04, 0.1),  # tail
        ],
    ),
    (
        "bear",
        [
            ("ellipse", 0.5, 0.55, 0.3, 0.32),  # body
            ("circle", 0.5, 0.28, 0.18),  # head
            ("circle", 0.36, 0.18, 0.06),  # left ear
            ("circle", 0.64, 0.18, 0.06),  # right ear
            ("ellipse", 0.38, 0.8, 0.07, 0.1),  # left leg
            ("ellipse", 0.62, 0.8, 0.07, 0.1),  # right leg
        ],
    ),
    (
        "rabbit",
        [
            ("ellipse", 0.5, 0.6, 0.2, 0.25),  # body
            ("circle", 0.5, 0.38, 0.13),  # head
            ("ellipse", 0.44, 0.18, 0.04, 0.15),  # left ear
            ("ellipse", 0.56, 0.18, 0.04, 0.15),  # right ear
            ("ellipse", 0.42, 0.8, 0.05, 0.08),  # left leg
            ("ellipse", 0.58, 0.8, 0.05, 0.08),  # right leg
            ("circle", 0.5, 0.85, 0.05),  # tail
        ],
    ),
    (
        "fox",
        [
            ("ellipse", 0.5, 0.55, 0.25, 0.25),  # body
            ("circle", 0.5, 0.3, 0.14),  # head
            ("polygon", [(0.38, 0.28), (0.32, 0.12), (0.44, 0.22)]),  # left ear
            ("polygon", [(0.62, 0.28), (0.68, 0.12), (0.56, 0.22)]),  # right ear
            ("polygon", [(0.5, 0.32), (0.45, 0.42), (0.55, 0.42)]),  # snout
            ("ellipse", 0.75, 0.65, 0.1, 0.06),  # tail
            ("ellipse", 0.38, 0.78, 0.04, 0.1),  # left leg
            ("ellipse", 0.62, 0.78, 0.04, 0.1),  # right leg
        ],
    ),
    (
        "owl",
        [
            ("ellipse", 0.5, 0.55, 0.22, 0.28),  # body
            ("circle", 0.5, 0.3, 0.16),  # head
            ("circle", 0.43, 0.28, 0.06),  # left eye ring
            ("circle", 0.57, 0.28, 0.06),  # right eye ring
            ("polygon", [(0.5, 0.32), (0.47, 0.38), (0.53, 0.38)]),  # beak
            ("polygon", [(0.35, 0.2), (0.32, 0.12), (0.4, 0.2)]),  # left ear tuft
            ("polygon", [(0.65, 0.2), (0.68, 0.12), (0.6, 0.2)]),  # right ear tuft
        ],
    ),
    (
        "penguin",
        [
            ("ellipse", 0.5, 0.55, 0.2, 0.32),  # body
            ("circle", 0.5, 0.28, 0.12),  # head
            ("ellipse", 0.3, 0.5, 0.06, 0.15),  # left wing
            ("ellipse", 0.7, 0.5, 0.06, 0.15),  # right wing
            ("ellipse", 0.44, 0.88, 0.06, 0.03),  # left foot
            ("ellipse", 0.56, 0.88, 0.06, 0.03),  # right foot
            ("polygon", [(0.5, 0.3), (0.47, 0.36), (0.53, 0.36)]),  # beak
        ],
    ),
    (
        "elephant",
        [
            ("ellipse", 0.5, 0.5, 0.32, 0.3),  # body
            ("circle", 0.3, 0.32, 0.16),  # head
            ("ellipse", 0.18, 0.32, 0.1, 0.14),  # left ear
            ("ellipse", 0.22, 0.55, 0.04, 0.15),  # trunk
            ("ellipse", 0.35, 0.78, 0.06, 0.12),  # front left leg
            ("ellipse", 0.65, 0.78, 0.06, 0.12),  # back right leg
        ],
    ),
    (
        "whale",
        [
            ("ellipse", 0.45, 0.5, 0.35, 0.18),  # body
            ("polygon", [(0.78, 0.42), (0.88, 0.32), (0.88, 0.58)]),  # tail fin
            ("polygon", [(0.4, 0.42), (0.35, 0.3), (0.45, 0.38)]),  # top fin
            ("circle", 0.18, 0.48, 0.03),  # eye
        ],
    ),
    (
        "dolphin",
        [
            ("ellipse", 0.48, 0.5, 0.32, 0.12),  # body
            ("polygon", [(0.15, 0.48), (0.1, 0.42), (0.18, 0.45)]),  # nose
            ("polygon", [(0.78, 0.45), (0.88, 0.35), (0.88, 0.55)]),  # tail
            ("polygon", [(0.45, 0.42), (0.42, 0.3), (0.5, 0.4)]),  # dorsal fin
            ("ellipse", 0.35, 0.56, 0.06, 0.03),  # flipper
        ],
    ),
    (
        "turtle",
        [
            ("ellipse", 0.5, 0.5, 0.28, 0.2),  # shell
            ("circle", 0.25, 0.5, 0.08),  # head
            ("ellipse", 0.35, 0.68, 0.06, 0.04),  # front left leg
            ("ellipse", 0.65, 0.68, 0.06, 0.04),  # back left leg
            ("ellipse", 0.35, 0.35, 0.06, 0.04),  # front right leg
            ("ellipse", 0.65, 0.35, 0.06, 0.04),  # back right leg
        ],
    ),
    (
        "frog",
        [
            ("ellipse", 0.5, 0.55, 0.25, 0.2),  # body
            ("ellipse", 0.5, 0.38, 0.18, 0.1),  # head
            ("circle", 0.38, 0.32, 0.06),  # left eye
            ("circle", 0.62, 0.32, 0.06),  # right eye
            ("ellipse", 0.35, 0.72, 0.08, 0.05),  # left leg
            ("ellipse", 0.65, 0.72, 0.08, 0.05),  # right leg
        ],
    ),
    (
        "butterfly",
        [
            ("ellipse", 0.5, 0.5, 0.03, 0.2),  # body
            ("ellipse", 0.35, 0.4, 0.14, 0.18),  # top left wing
            ("ellipse", 0.65, 0.4, 0.14, 0.18),  # top right wing
            ("ellipse", 0.37, 0.6, 0.1, 0.12),  # bottom left wing
            ("ellipse", 0.63, 0.6, 0.1, 0.12),  # bottom right wing
            ("polygon", [(0.47, 0.28), (0.43, 0.18), (0.46, 0.28)]),  # left antenna
            ("polygon", [(0.53, 0.28), (0.57, 0.18), (0.54, 0.28)]),  # right antenna
        ],
    ),
    (
        "bird",
        [
            ("ellipse", 0.5, 0.5, 0.2, 0.15),  # body
            ("circle", 0.32, 0.42, 0.1),  # head
            ("polygon", [(0.22, 0.42), (0.15, 0.4), (0.22, 0.45)]),  # beak
            ("polygon", [(0.65, 0.42), (0.8, 0.35), (0.72, 0.48)]),  # tail
            ("polygon", [(0.45, 0.4), (0.35, 0.25), (0.55, 0.38)]),  # wing
        ],
    ),
    (
        "fish",
        [
            ("ellipse", 0.45, 0.5, 0.25, 0.15),  # body
            ("polygon", [(0.72, 0.5), (0.85, 0.35), (0.85, 0.65)]),  # tail
            ("polygon", [(0.4, 0.4), (0.35, 0.3), (0.45, 0.38)]),  # top fin
            ("circle", 0.28, 0.48, 0.03),  # eye
        ],
    ),
    (
        "horse",
        [
            ("ellipse", 0.52, 0.5, 0.28, 0.2),  # body
            ("ellipse", 0.28, 0.32, 0.08, 0.12),  # head
            ("polygon", [(0.25, 0.25), (0.22, 0.15), (0.3, 0.22)]),  # ear
            ("ellipse", 0.32, 0.22, 0.08, 0.04),  # mane
            ("ellipse", 0.38, 0.72, 0.04, 0.15),  # front left leg
            ("ellipse", 0.66, 0.72, 0.04, 0.15),  # back left leg
            ("ellipse", 0.8, 0.55, 0.04, 0.12),  # tail
        ],
    ),
    (
        "deer",
        [
            ("ellipse", 0.52, 0.55, 0.25, 0.2),  # body
            ("ellipse", 0.3, 0.35, 0.08, 0.1),  # head
            ("polygon", [(0.28, 0.28), (0.2, 0.1), (0.25, 0.2)]),  # left antler
            ("polygon", [(0.34, 0.28), (0.4, 0.1), (0.36, 0.2)]),  # right antler
            ("ellipse", 0.38, 0.75, 0.03, 0.14),  # front leg
            ("ellipse", 0.66, 0.75, 0.03, 0.14),  # back leg
            ("circle", 0.76, 0.52, 0.04),  # tail
        ],
    ),
    (
        "wolf",
        [
            ("ellipse", 0.52, 0.55, 0.28, 0.22),  # body
            ("ellipse", 0.28, 0.35, 0.1, 0.12),  # head
            ("polygon", [(0.22, 0.28), (0.18, 0.15), (0.26, 0.24)]),  # left ear
            ("polygon", [(0.34, 0.28), (0.38, 0.15), (0.3, 0.24)]),  # right ear
            ("polygon", [(0.2, 0.38), (0.14, 0.36), (0.18, 0.42)]),  # snout
            ("ellipse", 0.38, 0.78, 0.04, 0.12),  # front leg
            ("ellipse", 0.66, 0.78, 0.04, 0.12),  # back leg
            ("ellipse", 0.8, 0.5, 0.06, 0.1),  # tail
        ],
    ),
    (
        "lion",
        [
            ("ellipse", 0.55, 0.55, 0.28, 0.24),  # body
            ("circle", 0.3, 0.35, 0.18),  # mane
            ("circle", 0.3, 0.35, 0.12),  # head (on top of mane)
            ("polygon", [(0.22, 0.38), (0.16, 0.36), (0.2, 0.42)]),  # snout
            ("ellipse", 0.4, 0.78, 0.05, 0.12),  # front leg
            ("ellipse", 0.68, 0.78, 0.05, 0.12),  # back leg
            ("ellipse", 0.82, 0.5, 0.04, 0.08),  # tail tip
        ],
    ),
    (
        "panda",
        [
            ("ellipse", 0.5, 0.58, 0.28, 0.28),  # body
            ("circle", 0.5, 0.3, 0.17),  # head
            ("circle", 0.37, 0.2, 0.06),  # left ear
            ("circle", 0.63, 0.2, 0.06),  # right ear
            ("ellipse", 0.42, 0.28, 0.06, 0.05),  # left eye patch
            ("ellipse", 0.58, 0.28, 0.06, 0.05),  # right eye patch
            ("ellipse", 0.38, 0.78, 0.06, 0.1),  # left leg
            ("ellipse", 0.62, 0.78, 0.06, 0.1),  # right leg
        ],
    ),
    (
        "koala",
        [
            ("ellipse", 0.5, 0.58, 0.22, 0.25),  # body
            ("circle", 0.5, 0.32, 0.16),  # head
            ("circle", 0.35, 0.28, 0.08),  # left ear (fluffy)
            ("circle", 0.65, 0.28, 0.08),  # right ear (fluffy)
            ("ellipse", 0.5, 0.38, 0.05, 0.04),  # nose
            ("ellipse", 0.38, 0.75, 0.06, 0.08),  # left arm
            ("ellipse", 0.62, 0.75, 0.06, 0.08),  # right arm
        ],
    ),
    (
        "hamster",
        [
            ("ellipse", 0.5, 0.55, 0.24, 0.25),  # body
            ("circle", 0.5, 0.32, 0.16),  # head
            ("circle", 0.36, 0.22, 0.05),  # left ear
            ("circle", 0.64, 0.22, 0.05),  # right ear
            ("ellipse", 0.4, 0.35, 0.06, 0.04),  # left cheek
            ("ellipse", 0.6, 0.35, 0.06, 0.04),  # right cheek
            ("ellipse", 0.42, 0.78, 0.05, 0.06),  # left foot
            ("ellipse", 0.58, 0.78, 0.05, 0.06),  # right foot
        ],
    ),
    (
        "duck",
        [
            ("ellipse", 0.52, 0.55, 0.25, 0.2),  # body
            ("circle", 0.3, 0.38, 0.12),  # head
            ("ellipse", 0.2, 0.4, 0.08, 0.03),  # bill
            ("polygon", [(0.72, 0.5), (0.82, 0.42), (0.78, 0.55)]),  # tail
            ("ellipse", 0.48, 0.48, 0.12, 0.08),  # wing
        ],
    ),
    (
        "pig",
        [
            ("ellipse", 0.5, 0.55, 0.28, 0.25),  # body
            ("circle", 0.5, 0.32, 0.15),  # head
            ("ellipse", 0.5, 0.38, 0.07, 0.04),  # snout
            ("polygon", [(0.38, 0.25), (0.35, 0.15), (0.42, 0.22)]),  # left ear
            ("polygon", [(0.62, 0.25), (0.65, 0.15), (0.58, 0.22)]),  # right ear
            ("ellipse", 0.38, 0.78, 0.05, 0.1),  # left leg
            ("ellipse", 0.62, 0.78, 0.05, 0.1),  # right leg
            ("ellipse", 0.78, 0.55, 0.04, 0.04),  # curly tail
        ],
    ),
    (
        "mouse",
        [
            ("ellipse", 0.5, 0.55, 0.2, 0.18),  # body
            ("circle", 0.5, 0.35, 0.12),  # head
            ("circle", 0.38, 0.25, 0.07),  # left ear
            ("circle", 0.62, 0.25, 0.07),  # right ear
            ("polygon", [(0.5, 0.4), (0.45, 0.46), (0.55, 0.46)]),  # nose
            ("ellipse", 0.72, 0.6, 0.12, 0.02),  # tail
        ],
    ),
    (
        "snake",
        [
            ("ellipse", 0.3, 0.5, 0.12, 0.1),  # head
            ("ellipse", 0.42, 0.55, 0.1, 0.08),  # body segment 1
            ("ellipse", 0.55, 0.48, 0.1, 0.08),  # body segment 2
            ("ellipse", 0.67, 0.55, 0.1, 0.08),  # body segment 3
            ("ellipse", 0.78, 0.5, 0.08, 0.06),  # tail
            ("polygon", [(0.2, 0.5), (0.14, 0.48), (0.14, 0.52)]),  # tongue
        ],
    ),
    (
        "octopus",
        [
            ("circle", 0.5, 0.35, 0.18),  # head
            ("ellipse", 0.3, 0.6, 0.04, 0.2),  # tentacle 1
            ("ellipse", 0.38, 0.62, 0.04, 0.2),  # tentacle 2
            ("ellipse", 0.46, 0.63, 0.04, 0.2),  # tentacle 3
            ("ellipse", 0.54, 0.63, 0.04, 0.2),  # tentacle 4
            ("ellipse", 0.62, 0.62, 0.04, 0.2),  # tentacle 5
            ("ellipse", 0.7, 0.6, 0.04, 0.2),  # tentacle 6
        ],
    ),
    (
        "bat",
        [
            ("ellipse", 0.5, 0.5, 0.08, 0.12),  # body
            ("circle", 0.5, 0.35, 0.08),  # head
            ("polygon", [(0.38, 0.28), (0.35, 0.2), (0.42, 0.3)]),  # left ear
            ("polygon", [(0.62, 0.28), (0.65, 0.2), (0.58, 0.3)]),  # right ear
            ("polygon", [(0.42, 0.4), (0.15, 0.3), (0.2, 0.6), (0.42, 0.55)]),  # left wing
            ("polygon", [(0.58, 0.4), (0.85, 0.3), (0.8, 0.6), (0.58, 0.55)]),  # right wing
        ],
    ),
    (
        "hedgehog",
        [
            ("ellipse", 0.5, 0.55, 0.28, 0.2),  # body
            ("circle", 0.3, 0.52, 0.1),  # head
            ("polygon", [(0.45, 0.38), (0.42, 0.28), (0.5, 0.36)]),  # spine 1
            ("polygon", [(0.55, 0.36), (0.52, 0.25), (0.58, 0.34)]),  # spine 2
            ("polygon", [(0.65, 0.38), (0.62, 0.28), (0.68, 0.36)]),  # spine 3
            ("polygon", [(0.72, 0.42), (0.7, 0.32), (0.76, 0.4)]),  # spine 4
            ("ellipse", 0.4, 0.72, 0.04, 0.06),  # left foot
            ("ellipse", 0.6, 0.72, 0.04, 0.06),  # right foot
        ],
    ),
    (
        "squirrel",
        [
            ("ellipse", 0.48, 0.55, 0.2, 0.2),  # body
            ("circle", 0.38, 0.35, 0.1),  # head
            ("polygon", [(0.32, 0.28), (0.28, 0.18), (0.35, 0.25)]),  # left ear
            ("polygon", [(0.42, 0.28), (0.45, 0.18), (0.4, 0.25)]),  # right ear
            ("ellipse", 0.72, 0.4, 0.08, 0.2),  # tail (big fluffy)
            ("ellipse", 0.42, 0.75, 0.04, 0.08),  # left leg
            ("ellipse", 0.56, 0.75, 0.04, 0.08),  # right leg
        ],
    ),
]

ANIMAL_COUNT = len(ANIMALS)
