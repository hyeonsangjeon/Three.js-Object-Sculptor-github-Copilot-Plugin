#!/usr/bin/env python3
"""Build validated showcase ObjectSculptSpec files for README demonstrations."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from new_sculpt_spec import make_spec  # noqa: E402
from sculpt_dna_core import make_default_sculpt_dna  # noqa: E402
from validate_sculpt_spec import validate_spec  # noqa: E402


PASS_IDS = [
    "blockout",
    "structural-pass",
    "form-refinement",
    "material-pass",
    "surface-pass",
    "lighting-pass",
    "interaction-pass",
    "optimization-pass",
]


def material(
    material_id: str,
    name: str,
    palette: list[str],
    roughness: float,
    *,
    metalness: float = 0.0,
    emissive: str | None = None,
) -> dict[str, Any]:
    value: dict[str, Any] = {
        "id": material_id,
        "name": name,
        "type": "physical",
        "shaderModel": "MeshPhysicalMaterial",
        "baseColor": palette[0],
        "color": palette[0],
        "albedo": {
            "dominant": palette[0],
            "secondary": palette[1:],
            "samplingNotes": f"Reference-derived palette for {name}.",
        },
        "colorVariation": {
            "palette": palette,
            "pattern": "deterministic regional variation",
            "amplitude": 0.18,
            "heightCorrelation": 0.15,
        },
        "textureResolution": 1024,
        "textureProjection": {
            "mode": "object-space",
            "repeat": [2.0, 2.0],
            "anisotropy": 8,
            "texelDensityIntent": "Keep detail stable across deterministic variants.",
        },
        "surfaceFrequencyBands": [
            {"id": "macro", "frequency": 2.0, "amplitude": 0.24, "role": "broad value zones"},
            {"id": "meso", "frequency": 12.0, "amplitude": 0.12, "role": "panel or surface breakup"},
            {"id": "micro", "frequency": 56.0, "amplitude": 0.035, "role": "highlight breakup"},
        ],
        "roughness": {
            "base": roughness,
            "variation": 0.12,
            "map": f"independent-{material_id}-roughness-field",
            "localResponse": "Cavities are rougher and exposed edges are smoother.",
        },
        "metalness": {"base": metalness, "variation": 0.05 if metalness else 0.0},
        "normal": {
            "pattern": f"independent-{material_id}-normal-field",
            "strength": 0.26,
            "scale": 24.0,
            "space": "tangent",
        },
        "bump": {"pattern": "micro surface", "amplitude": 0.02, "scale": 48.0},
        "displacement": {"pattern": "none", "amplitude": 0.0, "scale": 1.0, "silhouetteAffects": False},
        "ambientOcclusion": {
            "cavityStrength": 0.28,
            "contactShadowBias": 0.35,
            "notes": "Concentrate AO at component contacts.",
        },
        "wear": {"edgeWear": 0.08, "scratches": [], "chips": []},
        "dirt": {"amount": 0.08, "cavityBias": 0.55, "color": "#1A1A18"},
        "localOverrides": [
            {
                "id": f"{material_id}-contact-zone",
                "region": "component contact and lower-facing regions",
                "changes": "increase AO and roughness without flattening albedo",
                "strength": 0.35,
                "evidenceRefs": ["full-object"],
            }
        ],
        "shaderNotes": ["Generate albedo, roughness, normal, and AO independently."],
    }
    if emissive:
        value["emissive"] = {"color": emissive, "intensity": 1.8}
    return value


def action_profile(component_id: str, collider: str = "box") -> dict[str, Any]:
    return {
        "animationRole": "root" if component_id == "root" else "static",
        "pivot": {
            "mode": "base" if component_id == "root" else "center",
            "localPosition": [0, 0, 0],
            "axis": [0, 1, 0],
            "confidence": 0.8,
        },
        "transformChannels": {
            "translate": component_id == "root",
            "rotate": True,
            "scale": True,
            "visibility": True,
            "materialState": True,
        },
        "sockets": [],
        "collider": {
            "type": collider,
            "offset": [0, 0, 0],
            "scale": [1, 1, 1],
            "isTrigger": False,
        },
        "constraints": [],
        "destruction": {
            "breakable": component_id != "root",
            "fractureGroup": component_id,
            "seamRefs": [],
            "detachableFragments": [],
            "breakImpulse": 4.0 if component_id != "root" else 0.0,
            "debrisMaterial": "base",
        },
    }


def component(
    component_id: str,
    name: str,
    level: str,
    role: str,
    primitive: str,
    material_id: str,
    dimensions: list[float],
    position: list[float],
    *,
    parent: str | None = None,
    features: list[str] | None = None,
    evidence: list[str] | None = None,
) -> dict[str, Any]:
    local_features = [
        {
            "id": f"{component_id}-feature-{index + 1}",
            "type": feature,
            "placement": name,
            "size": "reference-relative",
            "geometryEffect": "procedural geometry or instancing",
            "materialEffect": "local material override",
            "confidence": 0.78,
        }
        for index, feature in enumerate(features or [])
    ]
    return {
        "id": component_id,
        "name": name,
        "level": level,
        "role": role,
        "importance": 1.0 if component_id == "root" else 0.78,
        "confidence": 0.82,
        "primitive": primitive,
        "geometryDescriptor": {
            "topologyIntent": f"Procedural {primitive} representation for {name}.",
            "edgeTreatment": {"type": "controlled bevel", "bevelRadius": 0.04, "segments": 2},
            "deformationStack": [],
            "uvStrategy": "object-space procedural coordinates",
            "normalStrategy": "smooth generated normals plus procedural normal map",
        },
        "parent": parent,
        "attachment": None,
        "dimensions": {
            "width": dimensions[0],
            "height": dimensions[1],
            "depth": dimensions[2],
            "units": "relative",
            "confidence": 0.8,
        },
        "transform": {"position": position, "rotation": [0, 0, 0]},
        "actionProfile": action_profile(component_id),
        "material": material_id,
        "materialLayers": [material_id],
        "deformations": [],
        "joints": [],
        "seams": [],
        "localFeatures": local_features,
        "surfaceDetail": {
            "macroRoughness": 0.24,
            "microRoughness": 0.48,
            "bumpAmplitude": 0.025,
            "normalPattern": "component-specific procedural detail",
            "displacementPattern": "",
            "occlusionPattern": "contact AO",
            "edgeWearPattern": "subtle exposed-edge response",
            "notes": "",
        },
        "evidenceRefs": evidence or ["full-object"],
        "details": [name],
        "fidelityTier": "blockout" if level == "macro" else "structural-pass",
    }


def evidence(evidence_id: str, observations: list[str]) -> dict[str, Any]:
    return {
        "id": evidence_id,
        "view": "reference",
        "imageRegion": {"x": 0.0, "y": 0.0, "width": 1.0, "height": 1.0, "units": "normalized"},
        "observations": observations,
        "confidence": 0.82,
    }


def configure_base(
    spec: dict[str, Any],
    *,
    source: str,
    suitability: str,
    object_type: str,
    components: list[dict[str, Any]],
    materials: list[dict[str, Any]],
    repetitions: list[dict[str, Any]],
    viewpoints: list[str],
    feature_targets: list[dict[str, Any]],
    reasoning: list[str],
    definition: list[str],
) -> dict[str, Any]:
    macro_count = sum(item["level"] == "macro" for item in components)
    meso_count = sum(item["level"] == "meso" for item in components)
    micro_count = sum(len(item.get("localFeatures", [])) for item in components)
    spec["sourceImage"] = source
    spec["suitability"] = suitability
    spec["scores"] = {
        "object_isolation": 3 if suitability == "pass" else 1,
        "silhouette_readability": 3,
        "depth_inference": 2,
        "primitive_decomposition": 3,
        "material_procedurality": 3,
        "occlusion_risk": 1 if suitability == "pass" else 2,
        "interaction_fit": 3,
    }
    spec["preSpecAssessment"] = {
        "objectClass": {
            "primaryType": object_type,
            "formLanguage": ["procedural real-time reconstruction", "deterministic variant family"],
            "structureKind": ["hierarchical components", "repeated systems"],
            "motionPotential": ["turntable", "component state variation"],
            "materialFamilies": [item["name"] for item in materials],
            "notes": "Showcase assessment authored from the user-provided reference.",
        },
        "complexity": {
            "tier": "complex",
            "scores": {
                "silhouetteComplexity": 3,
                "componentCount": 3,
                "hierarchyDepth": 2,
                "repetitionDensity": 3,
                "materialLayerCount": 3,
                "localDetailDensity": 2,
                "occlusionRisk": 2,
                "actionReadinessNeed": 2,
            },
            "estimatedCounts": {
                "macroComponents": macro_count,
                "mesoComponents": meso_count,
                "microFeatureGroups": micro_count,
                "materialLayers": len(materials),
                "repetitionSystems": len(repetitions),
            },
            "reasoning": reasoning,
        },
        "specDepthDecision": {
            "requiredDepth": "complex",
            "minimumComponentLevels": ["macro", "meso", "micro"],
            "needsRepetitionSystems": True,
            "needsMaterialLocalOverrides": True,
            "needsMultipleReviewViews": True,
            "needsActionReadyHierarchy": True,
            "rationale": "The README showcase must expose recognizable structure and controlled variation.",
        },
        "unknownsToResolveBeforeImplementation": [],
        "sourceImage": source,
    }
    spec["qualityContract"] = {
        "qualityBar": "complex",
        "definitionOfDone": definition,
        "minimumSpecDepth": {
            "macroComponents": macro_count,
            "mesoComponents": meso_count,
            "microFeatureGroups": micro_count,
            "materialLayers": len(materials),
            "repetitionSystems": len(repetitions),
            "reviewViewpoints": len(viewpoints),
        },
        "featureGroups": [
            {
                "id": target["id"],
                "name": target["name"],
                "required": target.get("mustPass", False),
                "qualityCriteria": [f"{target['name']} remains recognizable across variants."],
                "evidenceRefs": target["evidenceRefs"],
                "failureModes": [f"{target['name']} becomes generic or visually detached."],
            }
            for target in feature_targets[:5]
        ],
        "visualDeltaChecks": [
            "silhouette and proportion delta",
            "component hierarchy delta",
            "material palette and roughness delta",
            "repetition density delta",
        ],
        "antiShallowSpecRules": [
            "Do not generate the showcase from a single undifferentiated mesh.",
            "Do not vary protected component IDs, parent links, or review targets.",
            "Do not accept variants without fresh visual evidence.",
        ],
    }
    spec["qualityTargets"]["targetFidelity"] = 0.72
    spec["qualityTargets"]["mustMatch"] = [target["name"] for target in feature_targets if target.get("mustPass")]
    spec["qualityTargets"]["reviewViewpoints"] = viewpoints
    spec["featureReviewTargets"] = feature_targets
    spec["viewEvidence"] = [
        evidence("full-object", reasoning),
        evidence("identity-details", definition),
    ]
    spec["componentTree"] = components
    spec["materials"] = materials
    spec["repetitionSystems"] = repetitions
    all_ids = [item["id"] for item in components]
    spec["buildPasses"] = [
        {
            "id": pass_id,
            "goal": f"Complete the {pass_id} showcase gate.",
            "componentRefs": all_ids,
            "acceptance": [
                f"{pass_id} preserves identity-defining systems.",
                "Visual evidence meets the configured AI-vision threshold.",
            ],
        }
        for pass_id in PASS_IDS
    ]
    spec["sculptPipeline"]["passOrder"] = PASS_IDS
    spec["sculptPipeline"]["currentPass"] = "blockout"
    spec["sculptPipeline"]["completedPasses"] = []
    spec["lookDevTargets"]["qualityPriority"] = "balanced"
    spec["lookDevTargets"]["materialPass"]["referencePbrExtraction"]["requiredWhenSourceImagePresent"] = False
    spec["performanceBudget"] = {
        "qualityPriority": "balanced",
        "targetTriangles": 120000,
        "maxDrawCalls": 80,
        "textureSize": 1024,
        "fpsTarget": 45,
        "optimizationPolicy": "Preserve the README silhouette before reducing repeated detail.",
    }
    spec["lightingFromPhoto"] = [
        "Key light: soft sun or warm studio key with readable shadows.",
        "Fill light: cool sky fill preserving material midtones.",
        "Rim/environment light: subtle separation from the background.",
        "Exposure and tone mapping: ACES Filmic with controlled highlights.",
        "Contact shadow: ground and component-contact anchoring.",
    ]
    spec["proceduralStrategy"] = [
        "Build macro silhouette before repeated details.",
        "Use deterministic seeds for repeated systems.",
        "Keep variant controls semantic and bounded.",
        "Render three promoted variants from one camera for README comparison.",
    ]
    spec["animationAnchors"] = ["root turntable pivot", "material-state controls"]
    spec["destructionAnchors"] = ["semantic component boundaries"]
    spec["risks"] = []
    spec["sculptDNA"] = make_default_sculpt_dna(spec)
    spec["sculptDNA"]["variantPolicy"]["defaultSeed"] = 20260711
    errors, warnings = validate_spec(spec)
    strict_errors = [warning for warning in warnings if warning.startswith("quality:")]
    if errors or strict_errors:
        raise ValueError(
            json.dumps({"target": spec["targetName"], "errors": errors, "quality": strict_errors}, indent=2)
        )
    return spec


def brick_spec() -> dict[str, Any]:
    spec = make_spec("Brick Off-Road Explorer", "assets/brick-offroad-reference.jpeg")
    spec["targetId"] = "brick-offroad"
    components = [
        component("root", "Long wheelbase chassis", "macro", "body", "box", "body-shell", [5.8, 0.7, 2.7], [0, 1.1, 0], features=["stepped rocker panels"]),
        component("cabin", "Enclosed cabin", "macro", "shell", "box", "body-shell", [2.5, 1.7, 2.5], [-0.6, 2.0, 0], parent="root", features=["angular windshield frame"]),
        component("cargo-bed", "Rear utility bed", "macro", "shell", "box", "dark-trim", [2.2, 1.0, 2.5], [1.9, 1.7, 0], parent="root", features=["open utility bed rails"]),
        component("hood", "Front hood", "meso", "shell", "box", "body-shell", [1.7, 0.65, 2.45], [-2.15, 1.65, 0], parent="root", features=["faceted hood panels"]),
        component("wheel-system", "Four wheel system", "meso", "ornament", "instanced-cluster", "rubber", [6.2, 1.7, 3.4], [0, 0.65, 0], parent="root", features=["deep tire sidewall", "visible hubs"]),
        component("roof-rack", "Roof expedition rack", "meso", "ornament", "box", "dark-trim", [2.8, 0.35, 2.45], [-0.35, 3.1, 0], parent="root", features=["roof light bar"]),
        component("glass-system", "Windshield and windows", "meso", "surface detail", "plane-card", "glass", [2.4, 1.1, 2.5], [-0.9, 2.25, 0], parent="root"),
        component("bumper", "Front recovery bumper", "meso", "ornament", "box", "accent", [0.45, 0.55, 2.8], [-3.05, 1.0, 0], parent="root", features=["tow points"]),
        component("lighting", "Headlights and roof lamps", "meso", "ornament", "instanced-cluster", "lamp", [3.2, 0.5, 2.4], [-1.2, 2.55, 0], parent="root", features=["paired headlight clusters"]),
    ]
    materials = [
        material("body-shell", "Olive body panels", ["#65704A", "#4C5937", "#78835B", "#8C9570"], 0.62),
        material("roof-shell", "Light roof panels", ["#D8D8D2", "#BFC2BC", "#ECECE6"], 0.58),
        material("dark-trim", "Dark structural trim", ["#171A19", "#2A2F2E", "#3E4543"], 0.7),
        material("accent", "Expedition accent panels", ["#D87927", "#E6B64C", "#3AA6A0", "#B75B32"], 0.52),
        material("rubber", "Tire rubber", ["#111311", "#222622", "#363C36"], 0.82),
        material("glass", "Smoky glazing", ["#182B30", "#29434A", "#5A7378"], 0.2, metalness=0.05),
        material("lamp", "Warm lamps", ["#FFB347", "#FFD782", "#FFF3C4"], 0.3, emissive="#FFD782"),
    ]
    repetitions = [
        {"id": "wheel-treads", "name": "Wheel tread blocks", "primitive": "instanced-cluster", "componentRefs": ["wheel-system"], "material": "rubber", "count": 64, "seed": 6103, "distribution": "four rings", "constraints": ["equal front and rear wheel spacing"]},
        {"id": "body-studs", "name": "Visible brick studs", "primitive": "instanced-cluster", "componentRefs": ["root", "hood", "cabin"], "material": "body-shell", "count": 72, "seed": 8831, "distribution": "panel grid with omissions", "constraints": ["preserve window and panel gaps"]},
        {"id": "roof-lamps", "name": "Roof rack lamps", "primitive": "instanced-cluster", "componentRefs": ["roof-rack", "lighting"], "material": "lamp", "count": 5, "seed": 331, "distribution": "centered row", "constraints": ["symmetrical spacing"]},
    ]
    targets = [
        {"id": "raised-4x4-silhouette", "name": "Raised four-wheel off-road silhouette", "tier": "critical", "passIds": ["blockout", "form-refinement"], "minimumScore": 0.78, "mustPass": True, "componentRefs": ["root", "wheel-system"], "evidenceRefs": ["full-object"]},
        {"id": "four-wheel-system", "name": "Four large tire and hub system", "tier": "critical", "passIds": ["structural-pass", "surface-pass"], "minimumScore": 0.78, "mustPass": True, "componentRefs": ["wheel-system"], "evidenceRefs": ["identity-details"]},
        {"id": "cabin-hood-bed", "name": "Cabin, hood, and rear utility-bed hierarchy", "tier": "critical", "passIds": ["structural-pass", "form-refinement"], "minimumScore": 0.76, "mustPass": True, "componentRefs": ["cabin", "hood", "cargo-bed"], "evidenceRefs": ["full-object"]},
        {"id": "roof-expedition-gear", "name": "Roof rack and lamp bar", "tier": "important", "passIds": ["structural-pass", "material-pass"], "minimumScore": 0.68, "mustPass": False, "componentRefs": ["roof-rack", "lighting"], "evidenceRefs": ["identity-details"]},
    ]
    return configure_base(
        spec,
        source="assets/brick-offroad-reference.jpeg",
        suitability="pass",
        object_type="hard-surface articulated off-road vehicle",
        components=components,
        materials=materials,
        repetitions=repetitions,
        viewpoints=["reference-three-quarter", "front", "side", "rear-three-quarter"],
        feature_targets=targets,
        reasoning=[
            "The vehicle is isolated and its raised four-wheel chassis, cabin, rear body, and wheel spacing are readable.",
            "Brick studs, tire treads, and roof lamps are deterministic repetition systems.",
            "Hidden underbody details are simplified for a browser-real-time showcase.",
        ],
        definition=[
            "The render reads as the same olive raised 4x4 expedition vehicle.",
            "Three variants preserve four-wheel topology while changing panel palette and repeated-detail density.",
        ],
    )


def seoul_spec() -> dict[str, Any]:
    spec = make_spec("Seoul Palace Layered Challenge", "assets/seoul-challenge-reference.jpeg")
    spec["targetId"] = "seoul-challenge"
    components = [
        component("root", "Palace and city terrain", "macro", "base", "box", "courtyard", [14, 0.35, 10], [0, 0, 0], features=["large ceremonial courtyard"]),
        component("palace-campus", "Palace campus", "macro", "architectural", "box", "palace-wall", [9, 2.8, 6], [1.2, 1.4, 0], parent="root", features=["layered hall hierarchy"]),
        component("mountain-backdrop", "Mountain backdrop", "macro", "background", "instanced-cluster", "mountain", [16, 5, 4], [0, 2.5, -7], parent="root", features=["three dominant ridgelines"]),
        component("main-hall", "Main palace hall", "meso", "architectural", "box", "palace-wall", [4.2, 1.6, 2.4], [2.2, 1.2, -1.5], parent="palace-campus", features=["dark multi-tier roof"]),
        component("front-gate", "Foreground ceremonial gate", "meso", "architectural", "box", "palace-wall", [3.8, 1.5, 1.2], [-3.7, 0.9, 3.0], parent="palace-campus", features=["central arch openings"]),
        component("roof-system", "Dark tiled roof system", "meso", "ornament", "instanced-cluster", "roof", [9.5, 1.2, 6.4], [1.0, 2.2, 0], parent="palace-campus", features=["upturned eave silhouettes"]),
        component("courtyard", "Open ceremonial courtyard", "meso", "base", "box", "courtyard", [7.0, 0.08, 4.5], [-1.0, 0.25, 1.0], parent="root", features=["pale central axis"]),
        component("wall-system", "Perimeter walls", "meso", "architectural", "instanced-cluster", "palace-wall", [10, 0.8, 7], [0.5, 0.6, 0], parent="root"),
        component("side-halls", "Secondary halls", "meso", "architectural", "instanced-cluster", "palace-wall", [8, 1.4, 5], [1.2, 0.9, 0.3], parent="root"),
        component("city-blocks", "Dense urban blocks", "meso", "background", "instanced-cluster", "city", [15, 3.5, 5], [-2, 1.7, -5], parent="root", features=["white low-rise density gradient"]),
        component("tree-belt", "Green tree belt", "meso", "background", "instanced-cluster", "vegetation", [13, 2, 4], [0, 1, -3.8], parent="root", features=["palace-to-city green buffer"]),
        component("foreground-road", "Foreground road and wall", "meso", "base", "box", "city", [14, 0.25, 1.6], [0, 0.3, 4.8], parent="root"),
    ]
    materials = [
        material("courtyard", "Warm sand courtyard", ["#C9B58B", "#E4D4AA", "#A99571"], 0.82),
        material("palace-wall", "Muted palace walls", ["#BDAE8C", "#7E4B3C", "#D6C8A7"], 0.72),
        material("roof", "Charcoal tiled roofs", ["#202827", "#34413F", "#111716"], 0.74),
        material("mountain", "Forested mountains", ["#254D36", "#376B49", "#183927"], 0.9),
        material("city", "Distant urban blocks", ["#CBD0CC", "#E2E4DF", "#9EA7A3"], 0.78),
        material("vegetation", "Palace tree belt", ["#39704A", "#5B8A58", "#254E35"], 0.88),
    ]
    repetitions = [
        {"id": "palace-roofs", "name": "Palace roof tiers", "primitive": "instanced-cluster", "componentRefs": ["roof-system", "main-hall", "side-halls"], "material": "roof", "count": 14, "seed": 1107, "distribution": "campus hierarchy", "constraints": ["main hall remains dominant"]},
        {"id": "urban-blocks", "name": "Urban building blocks", "primitive": "instanced-cluster", "componentRefs": ["city-blocks"], "material": "city", "count": 48, "seed": 711, "distribution": "dense rear band", "constraints": ["height below mountain skyline"]},
        {"id": "tree-clusters", "name": "Tree clusters", "primitive": "instanced-cluster", "componentRefs": ["tree-belt"], "material": "vegetation", "count": 72, "seed": 2026, "distribution": "palace edge and city buffer", "constraints": ["courtyard remains open"]},
        {"id": "mountain-peaks", "name": "Mountain peaks", "primitive": "instanced-cluster", "componentRefs": ["mountain-backdrop"], "material": "mountain", "count": 7, "seed": 37, "distribution": "left and right ridgelines", "constraints": ["central valley remains visible"]},
    ]
    targets = [
        {"id": "palace-campus-layout", "name": "Palace courtyard and hall hierarchy", "tier": "critical", "passIds": ["blockout", "structural-pass"], "minimumScore": 0.74, "mustPass": True, "componentRefs": ["palace-campus", "main-hall", "courtyard"], "evidenceRefs": ["full-object"]},
        {"id": "dark-roof-rhythm", "name": "Dark tiled roof rhythm", "tier": "critical", "passIds": ["structural-pass", "material-pass"], "minimumScore": 0.72, "mustPass": True, "componentRefs": ["roof-system", "main-hall", "side-halls"], "evidenceRefs": ["identity-details"]},
        {"id": "city-mountain-layers", "name": "City, tree belt, and mountain depth layers", "tier": "critical", "passIds": ["blockout", "lighting-pass"], "minimumScore": 0.72, "mustPass": True, "componentRefs": ["city-blocks", "tree-belt", "mountain-backdrop"], "evidenceRefs": ["full-object"]},
        {"id": "foreground-gate-axis", "name": "Foreground gate and ceremonial axis", "tier": "important", "passIds": ["structural-pass", "form-refinement"], "minimumScore": 0.66, "mustPass": False, "componentRefs": ["front-gate", "courtyard"], "evidenceRefs": ["identity-details"]},
    ]
    result = configure_base(
        spec,
        source="assets/seoul-challenge-reference.jpeg",
        suitability="conditional",
        object_type="layered architectural city-scene challenge",
        components=components,
        materials=materials,
        repetitions=repetitions,
        viewpoints=["reference-aerial", "palace-axis", "side-depth", "mountain-silhouette"],
        feature_targets=targets,
        reasoning=[
            "The photo contains a palace campus, roads, city blocks, vegetation, and mountain ridges rather than one isolated object.",
            "The showcase accepts a layered low-poly scene approximation instead of pretending to recover exact architecture.",
            "Variant controls change density and palette while preserving palace, city, and mountain ordering.",
        ],
        definition=[
            "The scene reads as a Seoul palace campus framed by dense city blocks and green mountain ridges.",
            "Three variants preserve the palace axis while changing roof, city-density, tree-density, and mountain systems.",
        ],
    )
    result["risks"] = [
        "The 842x476 crop is sufficient for macro layering but not exact facade or roof-tile reconstruction.",
        "This challenge demonstrates scene decomposition, not exact geospatial reconstruction.",
    ]
    return result


def write_spec(path: Path, spec: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(spec, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(path)


def main() -> int:
    write_spec(ROOT / "examples" / "brick-offroad" / "object-sculpt-spec.json", brick_spec())
    write_spec(ROOT / "examples" / "seoul-challenge" / "object-sculpt-spec.json", seoul_spec())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
