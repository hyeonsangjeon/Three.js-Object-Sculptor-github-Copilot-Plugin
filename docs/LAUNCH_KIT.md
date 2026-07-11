# threejs-sculpt-dna Launch Kit

## Canonical links

- Repository: https://github.com/hyeonsangjeon/threejs-sculpt-dna
- Live demo: https://hyeonsangjeon.github.io/threejs-sculpt-dna/
- Release: https://github.com/hyeonsangjeon/threejs-sculpt-dna/releases/tag/v0.4.3
- User guide: https://github.com/hyeonsangjeon/threejs-sculpt-dna/blob/main/docs/USER_GUIDE.md
- GitHub Copilot marketplace PR: https://github.com/github/copilot-plugins/pull/57
- Awesome Copilot submission: https://github.com/github/awesome-copilot/issues/2274

## Truthful headline facts

- GitHub Copilot plugin with two skills:
  - `object-to-threejs-procedural`
  - `sculpt-dna-variants`
- Reference validation, complexity assessment, staged sculpt passes, browser review, and action-ready hierarchy.
- Coverage Curator selects a broadly separated representative family from a larger safe candidate pool.
- Repolis Living Archive flagship:
  - 0 imported meshes
  - approximately 100ms runtime generation on the development machine
  - 17,761 branch vertices
  - 2,600 instanced leaves
  - 220 moss instances
  - 72 branch-following code glyphs
- The flagship is manually art-directed after automated specification and variant exploration. Do not describe every generated preview as flagship quality.
- MIT licensed.
- Official marketplace submissions are under review. The repository marketplace installation already works.

---

## English — long launch post

### Title

**I built a GitHub Copilot plugin that turns reference images into procedural Three.js asset families**

### Post

I have been working on `threejs-sculpt-dna`, a GitHub Copilot plugin for rebuilding objects from reference images as code-native procedural Three.js assets.

Instead of jumping directly from an image to a generic mesh, the workflow forces a technical sculpting loop:

1. validate whether the reference is reconstructable
2. estimate its complexity
3. decompose silhouette, components, materials, and surface details
4. build through locked passes: blockout → structure → form → materials → surface
5. compare browser screenshots with the reference and self-correct
6. preserve pivots, sockets, colliders, and destruction groups

The original feature is **Sculpt DNA**. It defines bounded semantic controls while protecting topology and action-ready invariants.

Its **Coverage Curator** generates a larger pool of safe deterministic candidates and greedily selects a small, broadly separated family instead of showing near-duplicate random variants.

For the flagship I took one selected direction and art-directed it into **Repolis Living Archive**:

- 0 imported meshes
- ~100ms runtime generation on my development machine
- 17,761 branch vertices
- 2,600 instanced leaves
- generated bark PBR
- moss, code glyphs, energy paths, sockets, colliders, and destruction groups

The README deliberately shows the difference between:

**Reference → Sculpt DNA exploration → final flagship**

Live demo: https://hyeonsangjeon.github.io/threejs-sculpt-dna/

Repository: https://github.com/hyeonsangjeon/threejs-sculpt-dna

Install:

```bash
copilot plugin marketplace add hyeonsangjeon/threejs-sculpt-dna
copilot plugin install threejs-sculpt-dna@threejs-copilot-plugins
```

It is MIT licensed. The default Copilot marketplace and Awesome Copilot submissions are currently under review.

Feedback on the sculpt workflow, Three.js output, and variant curation model would be very welcome.

---

## English — Show HN version

### Title

**Show HN: threejs-sculpt-dna – procedural 3D asset families with GitHub Copilot**

### Body

I built a GitHub Copilot plugin that reconstructs reference images as procedural Three.js code rather than imported meshes.

The pipeline validates the image, writes a structured sculpt spec, builds through locked visual passes, and records browser/vision evidence. Generated objects keep pivots, sockets, collider proxies, and destruction groups.

The new part is Sculpt DNA: bounded semantic parameters plus invariants. A Coverage Curator samples a larger safe pool and selects a broadly separated representative family.

The live Repolis Tree is the art-directed flagship produced after that exploration. It contains no imported mesh and generates roughly 17k branch vertices, 2.6k leaves, moss, code glyphs, energy paths, and runtime metadata in about 100ms on my machine.

Demo: https://hyeonsangjeon.github.io/threejs-sculpt-dna/

Source: https://github.com/hyeonsangjeon/threejs-sculpt-dna

MIT licensed. I would appreciate feedback on where this workflow is useful or unnecessarily strict.

---

## English — short social post

I built `threejs-sculpt-dna`, a GitHub Copilot plugin that turns reference images into procedural Three.js asset families.

Reference validation → locked sculpt passes → visual self-correction → Coverage Curator → art-directed flagship.

Repolis demo: https://hyeonsangjeon.github.io/threejs-sculpt-dna/

Source: https://github.com/hyeonsangjeon/threejs-sculpt-dna

#threejs #githubcopilot #proceduralgeneration

---

## 한국어 — 긴 소개글

### 제목

**GitHub Copilot로 레퍼런스 이미지를 절차적 Three.js 자산 패밀리로 만드는 플러그인을 공개했습니다**

### 본문

`threejs-sculpt-dna`라는 GitHub Copilot 플러그인을 만들었습니다.

레퍼런스 이미지를 바로 범용 메시로 바꾸는 대신, 기술 아티스트가 조형하는 과정을 코드 워크플로로 강제합니다.

1. 이미지가 절차적 재구성에 적합한지 검증
2. 복잡도와 필요한 스펙 깊이 평가
3. 실루엣, 구조 부품, 재질, 표면 디테일로 분해
4. blockout → structure → form → materials → surface 단계별 제작
5. 브라우저 스크린샷과 레퍼런스를 비교해 self-correction
6. 피벗, 소켓, collider, destruction group을 유지

우리 플러그인의 독자 기능은 **Sculpt DNA**입니다.

오브젝트 정체성을 깨지 않는 범위에서 재질, 반복 밀도, 비율 같은 의미 있는 파라미터를 정의하고, topology와 action-ready hierarchy를 invariant로 보호합니다.

여기에 **Coverage Curator**를 추가했습니다. 많은 안전 후보를 생성한 뒤 서로 비슷한 결과가 아니라 파라미터 공간을 넓게 대표하는 소수의 변형을 선택합니다.

플래그십은 **Repolis Living Archive**입니다.

- 외부 메시 0개
- 개발 머신 기준 약 100ms 런타임 생성
- branch vertex 17,761개
- instanced leaf 2,600개
- moss 220개
- 가지를 따라가는 code glyph 72개
- generated bark PBR, energy path, socket, collider, destruction group 포함

중요한 점은 README에서 다음 단계를 구분했다는 것입니다.

**Reference → Sculpt DNA 중간 탐색 → 최종 아트 디렉션 플래그십**

라이브 데모: https://hyeonsangjeon.github.io/threejs-sculpt-dna/

GitHub: https://github.com/hyeonsangjeon/threejs-sculpt-dna

설치:

```bash
copilot plugin marketplace add hyeonsangjeon/threejs-sculpt-dna
copilot plugin install threejs-sculpt-dna@threejs-copilot-plugins
```

MIT 라이선스이며, 현재 GitHub 기본 Copilot marketplace와 Awesome Copilot 등록 심사가 진행 중입니다.

조형 파이프라인이나 Three.js 결과물, variant curation 방식에 대한 피드백을 환영합니다.

---

## 한국어 — 짧은 SNS 버전

레퍼런스 이미지를 절차적 Three.js 자산 패밀리로 만드는 GitHub Copilot 플러그인 `threejs-sculpt-dna`를 공개했습니다.

이미지 검증 → 단계별 조형 → 브라우저 비교/수정 → Sculpt DNA → Coverage Curator → 최종 플래그십.

🌳 Live: https://hyeonsangjeon.github.io/threejs-sculpt-dna/

💻 GitHub: https://github.com/hyeonsangjeon/threejs-sculpt-dna

#threejs #githubcopilot #procedural3d

---

## Suggested posting order

1. GitHub Release and repository social preview
2. X/Threads short post with `assets/repolis-tree-hero.gif`
3. LinkedIn or blog long post with the three-stage README image flow
4. Hacker News after the default Copilot marketplace PR is approved
5. Korean developer communities with the Korean long post

## Recommended media

- First media: `assets/repolis-tree-hero.gif`
- Link preview: `assets/social-preview.png`
- Process explanation: README three-column Reference / DNA variants / Flagship table
- GitHub Copilot usage: `assets/github-copilot-image-prompt-example.png`

## Avoid these claims

- Do not say the flagship was produced with zero art direction.
- Do not call preview families production-ready.
- Do not claim exact photogrammetry or hidden-side reconstruction.
- Do not say the plugin is already in the default marketplaces until the submissions are approved.
