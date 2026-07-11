import type * as THREE from 'three';

export type RepolisStage =
  | 'blockout'
  | 'structural-pass'
  | 'form-refinement'
  | 'material-pass'
  | 'surface-pass'
  | 'full';

export type RepolisVariant = {
  id: string;
  label: string;
  foliageDensity: number;
  cyanRatio: number;
  amber: string;
  cyan: string;
  energy: string;
  branchWarmth: number;
};

export type RepolisHeroOptions = {
  seed?: number;
  variant?: number | string;
  stage?: RepolisStage;
};

export type RepolisHeroResult = {
  root: THREE.Group;
  runtime: Record<string, unknown>;
  stats: {
    generationMs: number;
    macroBranches: number;
    secondaryBranches: number;
    fineBranches: number;
    leafInstances: number;
    mossInstances: number;
    branchVertices: number;
    glyphInstances: number;
    importedMeshes: 0;
    stage: RepolisStage;
  };
  variant: RepolisVariant;
  update(elapsedSeconds: number): void;
  dispose(): void;
};

export const REPOLIS_VARIANTS: RepolisVariant[];
export const REPOLIS_STAGES: RepolisStage[];
export function createRepolisHero(options?: RepolisHeroOptions): RepolisHeroResult;
