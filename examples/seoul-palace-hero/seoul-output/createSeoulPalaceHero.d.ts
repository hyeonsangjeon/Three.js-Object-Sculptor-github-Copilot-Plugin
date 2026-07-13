import type * as THREE from 'three';

export type SeoulStage =
  | 'blockout'
  | 'structural-pass'
  | 'form-refinement'
  | 'material-pass'
  | 'surface-pass'
  | 'lighting-pass'
  | 'interaction-pass'
  | 'optimization-pass';

export type SeoulPalaceHeroOptions = {
  seed?: number | string;
  stage?: SeoulStage;
  variant?: SeoulVariantConfig;
};

export type SeoulVariantConfig = {
  id: string;
  seed?: number | string;
  roofRoughness: number;
  roofAccent: string;
  courtyardRoughness: number;
  courtyardTone: string;
  treeDensity: number;
  cityDensity: number;
  mountainForestDensity: number;
  mountainRockDensity: number;
  provenance?: Record<string, unknown>;
};

export type SeoulCollider = THREE.Object3D & {
  userData: {
    collider: {
      id: string;
      parentId: string;
      type: 'box';
      size: number[];
      isTrigger: false;
    };
  };
};

export type SeoulSocket = THREE.Object3D & {
  userData: {
    socketId: string;
    socket: {
      id: string;
      parentNodeId: string;
    };
  };
};

export type SeoulRuntime = {
  nodes: Record<string, THREE.Object3D>;
  meshes: Record<string, THREE.Mesh | THREE.InstancedMesh>;
  sockets: Record<string, SeoulSocket>;
  colliders: Record<string, SeoulCollider>;
  destructionGroups: Record<string, THREE.Object3D[]>;
  resources: {
    geometries: Set<THREE.BufferGeometry>;
    materials: Set<THREE.Material>;
    textures: Set<THREE.Texture>;
    instancedMeshes: Set<THREE.InstancedMesh>;
  };
};

export type SeoulPalaceHeroStats = {
  generationMs: number;
  seed: number;
  stage: SeoulStage;
  variantId: string;
  macroGroups: 6;
  nodes: number;
  meshes: number;
  sceneDrawables: number;
  triangles: number;
  instances: number;
  treeInstances: number;
  cityInstances: number;
  sockets: number;
  colliders: number;
  importedMeshes: 0;
  generatedTextureCount: number;
};

export type SeoulPalaceHeroResult = {
  root: THREE.Group;
  runtime: SeoulRuntime;
  groups: Record<string, THREE.Group>;
  materials: Record<string, THREE.MeshStandardMaterial>;
  stats: SeoulPalaceHeroStats;
  setLayerLens(mode: 'full' | 'palace' | 'city' | 'nature'): void;
  setGateOpen(amount: number): void;
  setTurntable(enabled: boolean): void;
  update(elapsedSeconds: number): void;
  dispose(): void;
};

export const SEOUL_STAGES: readonly SeoulStage[];
export const SEOUL_DEFAULT_SEED: number;
export const SEOUL_REFERENCE_CAMERA_VIEW: Readonly<{
  position: readonly [number, number, number];
  target: readonly [number, number, number];
  rotation: readonly [number, number, number];
}>;
export function createSeoulPalaceHero(options?: SeoulPalaceHeroOptions): SeoulPalaceHeroResult;
