# Changelog

## [0.2.4](https://github.com/Danube-Labs/javv-poc/compare/v0.2.3...v0.2.4) (2026-07-04)


### Features

* **m4:** scanner-disagreement flags — severity + count pair (D5a/D5b, slice 3) ([#124](https://github.com/Danube-Labs/javv-poc/issues/124)) ([6dbdf7d](https://github.com/Danube-Labs/javv-poc/commit/6dbdf7d392ca4a52505c1f9ad2e2588980c650a7)), closes [#26](https://github.com/Danube-Labs/javv-poc/issues/26)
* **m4:** write aliases + lifecycle sweep — rollover & per-cluster retention (slices 1–2) ([#122](https://github.com/Danube-Labs/javv-poc/issues/122)) ([4631eca](https://github.com/Danube-Labs/javv-poc/commit/4631eca8a2774fe3306204c0942f2d34f85c17ab))

## [0.2.3](https://github.com/Danube-Labs/javv-poc/compare/v0.2.2...v0.2.3) (2026-07-03)


### Features

* **m3:** backend-allocated scan_order — D45, slice 1 of M3 ([#103](https://github.com/Danube-Labs/javv-poc/issues/103)) ([8719ac6](https://github.com/Danube-Labs/javv-poc/commit/8719ac62a4b36e0fd1e201dacc44abaf4987b8c2)), closes [#25](https://github.com/Danube-Labs/javv-poc/issues/25)
* **m3:** partial-doc merge — human triage survives rescans (D31, slice 2) ([#105](https://github.com/Danube-Labs/javv-poc/issues/105)) ([0080150](https://github.com/Danube-Labs/javv-poc/commit/00801503b3e030309834aa394aa26f6f0fc6223d)), closes [#25](https://github.com/Danube-Labs/javv-poc/issues/25)
* **m3:** per-digest watermark CAS — the create+update guard (D40, slice 3) ([#106](https://github.com/Danube-Labs/javv-poc/issues/106)) ([f5e217e](https://github.com/Danube-Labs/javv-poc/commit/f5e217e76d79ddb4de30d0f167a7ff5ef293b08d)), closes [#25](https://github.com/Danube-Labs/javv-poc/issues/25)
* **m3:** reconcile-on-commit — resolved CVEs leave the now grid (D37/D38, slice 5) ([#107](https://github.com/Danube-Labs/javv-poc/issues/107)) ([a4e4bd5](https://github.com/Danube-Labs/javv-poc/commit/a4e4bd56d13e4859d5bb58adf326ab63b47bb686)), closes [#25](https://github.com/Danube-Labs/javv-poc/issues/25)
* **m3:** two-timer staleness sweep — flag data the scanner stopped refreshing (D20, slice 6) ([#108](https://github.com/Danube-Labs/javv-poc/issues/108)) ([8972f2e](https://github.com/Danube-Labs/javv-poc/commit/8972f2ef8e67b614182effa1a499255c8c70ce66))


### Bug Fixes

* **m3:** audit follow-ups (M-1/M-4, m-1/m-3/m-4/m-5/m-7) ([#119](https://github.com/Danube-Labs/javv-poc/issues/119)) ([299a56f](https://github.com/Danube-Labs/javv-poc/commit/299a56fb59c155bfd7f7f46ab6d9aa7bb2e5f552))

## [0.2.2](https://github.com/Danube-Labs/javv-poc/compare/v0.2.1...v0.2.2) (2026-07-02)


### Features

* stamp effective_config on the envelope — schema v3 (D44/FR-25) ([#101](https://github.com/Danube-Labs/javv-poc/issues/101)) ([9f8331c](https://github.com/Danube-Labs/javv-poc/commit/9f8331cc544d1fc19e58de66f15d0288664408f8)), closes [#91](https://github.com/Danube-Labs/javv-poc/issues/91)


### Bug Fixes

* **scanner:** stamp trivy vuln-DB provenance via a per-cycle version call ([#99](https://github.com/Danube-Labs/javv-poc/issues/99)) ([5affa4a](https://github.com/Danube-Labs/javv-poc/commit/5affa4a8fa01433011482c7a6d1c90db341172f4)), closes [#96](https://github.com/Danube-Labs/javv-poc/issues/96)

## [0.2.1](https://github.com/Danube-Labs/javv-poc/compare/v0.2.0...v0.2.1) (2026-07-02)


### Features

* M2 snapshot/restore — durability early ([#88](https://github.com/Danube-Labs/javv-poc/issues/88)) ([cd110fe](https://github.com/Danube-Labs/javv-poc/commit/cd110fefce7e4671d3915af5113582a7e4a7534e))
* **scanner:** env-configurable Trivy/Grype scan flags ([#91](https://github.com/Danube-Labs/javv-poc/issues/91) phase 1) ([#92](https://github.com/Danube-Labs/javv-poc/issues/92)) ([fa65374](https://github.com/Danube-Labs/javv-poc/commit/fa653746a353112808e7c953ab11dead54e6df4e))
* UI-configurable scan scope via system-config ([#94](https://github.com/Danube-Labs/javv-poc/issues/94), D43/FR-24) ([#95](https://github.com/Danube-Labs/javv-poc/issues/95)) ([8c26032](https://github.com/Danube-Labs/javv-poc/commit/8c26032b43847c43c74e119649231161e37e1140))

## [0.2.0](https://github.com/Danube-Labs/javv-poc/compare/v0.1.2...v0.2.0) (2026-07-02)


### Features

* **backend:** hardened ingest endpoint + full-envelope contract (M1 slice 3) ([#83](https://github.com/Danube-Labs/javv-poc/issues/83)) ([a5d9a5d](https://github.com/Danube-Labs/javv-poc/commit/a5d9a5d988503608e99f1f530163fd33a6ca5da0)), closes [#23](https://github.com/Danube-Labs/javv-poc/issues/23)
* **backend:** M1 skeleton — app factory, lifespan, health, error envelope ([#76](https://github.com/Danube-Labs/javv-poc/issues/76)) ([4b1eb04](https://github.com/Danube-Labs/javv-poc/commit/4b1eb045b2ad633d6c8cd6048b91010a9ac3e9fa)), closes [#23](https://github.com/Danube-Labs/javv-poc/issues/23)
* **backend:** observability + CI OpenSearch service — M1 complete ([#85](https://github.com/Danube-Labs/javv-poc/issues/85)) ([b97ffcf](https://github.com/Danube-Labs/javv-poc/commit/b97ffcfd5221010beecb1316dd5d2fe841b1162d)), closes [#23](https://github.com/Danube-Labs/javv-poc/issues/23)
* **backend:** versioned index bootstrap (M1 slice 2) ([#82](https://github.com/Danube-Labs/javv-poc/issues/82)) ([ab15c79](https://github.com/Danube-Labs/javv-poc/commit/ab15c7976abced99fb9669e42c407dbd65b7601b))
* wire scanner auth to the ingest endpoint + token-mint CLI (e2e proven) ([#84](https://github.com/Danube-Labs/javv-poc/issues/84)) ([97ad07c](https://github.com/Danube-Labs/javv-poc/commit/97ad07cad9ea529536f371a8164b5b633228cd72))

## [0.1.2](https://github.com/Danube-Labs/javv-poc/compare/v0.1.1...v0.1.2) (2026-07-01)


### Features

* **scanner:** stamp observed topology on the envelope (schema v2) ([#77](https://github.com/Danube-Labs/javv-poc/issues/77)) ([8a2db1b](https://github.com/Danube-Labs/javv-poc/commit/8a2db1bebb31e96d3a9b520d1d090a74d933e59a)), closes [#23](https://github.com/Danube-Labs/javv-poc/issues/23)

## [0.1.1](https://github.com/Danube-Labs/javv-poc/compare/v0.1.0...v0.1.1) (2026-07-01)


### Bug Fixes

* **scanner:** isolate per-image scan failures + retrospective follow-ups ([#71](https://github.com/Danube-Labs/javv-poc/issues/71)) ([44d5072](https://github.com/Danube-Labs/javv-poc/commit/44d5072972db1743e7a6a0d276a417a22fdfde20))

## 0.1.0 (2026-06-30)


### Features

* M0 scanner package (discovery, adapters, normalize, envelope, push) ([#58](https://github.com/Danube-Labs/javv-poc/issues/58)) ([3f41eaf](https://github.com/Danube-Labs/javv-poc/commit/3f41eafdf42f11b679293b0bb2d1ed7be66ca425))
* M0b — scanner image publish + compatibility CI ([#63](https://github.com/Danube-Labs/javv-poc/issues/63)) ([f4002cf](https://github.com/Danube-Labs/javv-poc/commit/f4002cf710f89f49c5eb867b0d76386a86bee6d3))


### Bug Fixes

* correct tool-version probe (only kubectl/helm reject --version) ([#47](https://github.com/Danube-Labs/javv-poc/issues/47)) ([baa6422](https://github.com/Danube-Labs/javv-poc/commit/baa64227dc13488d1d0f13b989dd170c9f2ca603))
* setup-dev node install fails as root ($SUDO -E) ([cc34c17](https://github.com/Danube-Labs/javv-poc/commit/cc34c17f6828c73fea263b8be7efc13264ceb897))
