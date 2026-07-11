import type * as THREE from 'three';

export type BrickStage =
  | 'blockout'
  | 'structural-pass'
  | 'form-refinement'
  | 'material-pass'
  | 'surface-pass'
  | 'full';

export type BrickVariant = {
  id: string;
  label: string;
  body: string;
  bodyDark: string;
  bodyRoughness: number;
  roof: string;
  roofRoughness: number;
  trim: string;
  trimRoughness: number;
  accent: string;
  accentRoughness: number;
  rubber: string;
  rubberRoughness: number;
  glass: string;
  glassRoughness: number;
  lamp: string;
  lampRoughness: number;
  dust: string;
  wear: number;
  treadCount: number;
  studCount: number;
  roofLampCount: number;
};

export type BrickOffroadOptions = {
  seed?: number;
  variant?: number | string;
  stage?: BrickStage;
};

export type BrickOffroadStats = {
  generationMs: number;
  meshes: number;
  triangles: number;
  sceneDrawables: number;
  wheels: 4;
  treadInstances: number;
  treadsPerWheel: number;
  studInstances: number;
  roofLampInstances: number;
  importedMeshes: 0;
  generatedTextureResolution: number;
  stage: BrickStage;
};

export type BrickRuntime = {
  nodes: Record<string, THREE.Object3D>;
  meshes: Record<string, THREE.Mesh>;
  sockets: Record<string, THREE.Object3D>;
  colliders: Record<string, {
    id: string;
    parentId: string;
    type: string;
    center: number[];
    size: number[];
    isTrigger: boolean;
  }>;
  destructionGroups: Record<string, THREE.Mesh[]>;
  wheelPivots: THREE.Group[];
  steeringPivots: THREE.Group[];
  suspensionAnchors: THREE.Group[];
};

export type BrickOffroadResult = {
  root: THREE.Group;
  runtime: BrickRuntime;
  variant: BrickVariant;
  stats: BrickOffroadStats;
  update(elapsedSeconds: number): void;
  dispose(): void;
};

export const BRICK_STAGES: BrickStage[];
export const BRICK_VARIANTS: BrickVariant[];
export function createBrickOffroad(options?: BrickOffroadOptions): BrickOffroadResult;
