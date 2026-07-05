# Changelog

## [0.2.15](https://github.com/Danube-Labs/javv-poc/compare/v0.2.14...v0.2.15) (2026-07-05)


### Features

* **m6:** csv + vex export and the as-of-t dispatcher seam (slices 5-7) ([#181](https://github.com/Danube-Labs/javv-poc/issues/181)) ([f8393fa](https://github.com/Danube-Labs/javv-poc/commit/f8393fa8c213f96bcb88cbe574b8080a5f18e7a5))

## [0.2.14](https://github.com/Danube-Labs/javv-poc/compare/v0.2.13...v0.2.14) (2026-07-05)


### Features

* **logging:** structured per-request line — method/path/status/duration_ms fields ([#178](https://github.com/Danube-Labs/javv-poc/issues/178)) ([215b684](https://github.com/Danube-Labs/javv-poc/commit/215b684326ab4c37e200922548ff8c5d4c1cf374)), closes [#156](https://github.com/Danube-Labs/javv-poc/issues/156)
* **m6:** contributors — audit-log leaderboard, ttr, sla-hit % (slice 4) ([#177](https://github.com/Danube-Labs/javv-poc/issues/177)) ([70c6824](https://github.com/Danube-Labs/javv-poc/commit/70c6824e2da40a29efe272985878e58683cf29d2)), closes [#31](https://github.com/Danube-Labs/javv-poc/issues/31)

## [0.2.13](https://github.com/Danube-Labs/javv-poc/compare/v0.2.12...v0.2.13) (2026-07-05)


### Features

* **m6:** trends — committed scans by cardinality(commit_key) + new/resolved series (slice 3) ([#175](https://github.com/Danube-Labs/javv-poc/issues/175)) ([231eb34](https://github.com/Danube-Labs/javv-poc/commit/231eb343f6b6b9f8162a94b2fc11cb99b494cf14)), closes [#31](https://github.com/Danube-Labs/javv-poc/issues/31)

## [0.2.12](https://github.com/Danube-Labs/javv-poc/compare/v0.2.11...v0.2.12) (2026-07-05)


### Features

* **m6:** faceted findings search — PIT cursor paging + overdue decoration (slice 1) ([#170](https://github.com/Danube-Labs/javv-poc/issues/170)) ([c3ea427](https://github.com/Danube-Labs/javv-poc/commit/c3ea4275e0c9177f6c927f1c17076e609334babc)), closes [#31](https://github.com/Danube-Labs/javv-poc/issues/31)
* **m6:** scanner-faceted aggregations + composite group paging (slice 2) ([#172](https://github.com/Danube-Labs/javv-poc/issues/172)) ([cf2793c](https://github.com/Danube-Labs/javv-poc/commit/cf2793c0418ed3c3b24419e4e1cb82ef97394a1a))

## [0.2.11](https://github.com/Danube-Labs/javv-poc/compare/v0.2.10...v0.2.11) (2026-07-05)


### Bug Fixes

* **m6:** ingest stamp conflict 500 + the [#117](https://github.com/Danube-Labs/javv-poc/issues/117) refresh measurement bench ([#168](https://github.com/Danube-Labs/javv-poc/issues/168)) ([9b0d75e](https://github.com/Danube-Labs/javv-poc/commit/9b0d75ef4ed19bfafb86a924d56b7add39c40b14))

## [0.2.10](https://github.com/Danube-Labs/javv-poc/compare/v0.2.9...v0.2.10) (2026-07-05)


### Features

* **m5d:** SLA/overdue + bulk triage + risk-accept approval list ([#165](https://github.com/Danube-Labs/javv-poc/issues/165)) ([0f30705](https://github.com/Danube-Labs/javv-poc/commit/0f3070525df9188fd6540a0ec2fdeba0f9d548b1))

## [0.2.9](https://github.com/Danube-Labs/javv-poc/compare/v0.2.8...v0.2.9) (2026-07-05)


### Features

* **m5c:** decisions & projection — precedence ladder, D22 gate, reproject triggers, rebuild-state ([#163](https://github.com/Danube-Labs/javv-poc/issues/163)) ([f3bb822](https://github.com/Danube-Labs/javv-poc/commit/f3bb822acee8fed010f57c0ea2cd371c1d35a4a2))

## [0.2.8](https://github.com/Danube-Labs/javv-poc/compare/v0.2.7...v0.2.8) (2026-07-05)


### Features

* **observability:** shared logging lib, log levels, OpenSearch touch visibility ([#159](https://github.com/Danube-Labs/javv-poc/issues/159)) ([cdb1fce](https://github.com/Danube-Labs/javv-poc/commit/cdb1fce3f32583542417e21e0f3231db21e5e42d))

## [0.2.7](https://github.com/Danube-Labs/javv-poc/compare/v0.2.6...v0.2.7) (2026-07-05)


### Features

* **audit:** task d - admin user/role management (fr-18) ([#151](https://github.com/Danube-Labs/javv-poc/issues/151)) ([7b0a8ea](https://github.com/Danube-Labs/javv-poc/commit/7b0a8ea42551e7ca5e73c237bfb758909ab5a040)), closes [#141](https://github.com/Danube-Labs/javv-poc/issues/141)


### Bug Fixes

* **audit:** task a - triage/audit correctness (m-1, m-2, m-3) ([#148](https://github.com/Danube-Labs/javv-poc/issues/148)) ([960e117](https://github.com/Danube-Labs/javv-poc/commit/960e1171224fc9f29696fe458837aea56b19e413)), closes [#138](https://github.com/Danube-Labs/javv-poc/issues/138)
* **audit:** task c - auth hardening bundle ([#152](https://github.com/Danube-Labs/javv-poc/issues/152)) ([2ac20d6](https://github.com/Danube-Labs/javv-poc/commit/2ac20d607c573dd52cfd9f719def365ef7335b77)), closes [#140](https://github.com/Danube-Labs/javv-poc/issues/140)
* **audit:** task e - token admin polish ([#153](https://github.com/Danube-Labs/javv-poc/issues/153)) ([5b72c2c](https://github.com/Danube-Labs/javv-poc/commit/5b72c2cca64805ff46e3b100dee64f67477fb680)), closes [#142](https://github.com/Danube-Labs/javv-poc/issues/142)
* **audit:** task f - lifecycle/jobs robustness ([#154](https://github.com/Danube-Labs/javv-poc/issues/154)) ([4fa71a1](https://github.com/Danube-Labs/javv-poc/commit/4fa71a1c50990eacdc17182bd218c1a8bade8609)), closes [#143](https://github.com/Danube-Labs/javv-poc/issues/143)

## [0.2.6](https://github.com/Danube-Labs/javv-poc/compare/v0.2.5...v0.2.6) (2026-07-04)


### Features

* **m5b:** FR-7 state machine + the structured audit writer (slices 1–2) ([#133](https://github.com/Danube-Labs/javv-poc/issues/133)) ([6f56ca7](https://github.com/Danube-Labs/javv-poc/commit/6f56ca7d294046edeae078fd9145a031b068c4c4))
* **m5b:** triage service/route + decision lifecycle (slices 3–4) ([#136](https://github.com/Danube-Labs/javv-poc/issues/136)) ([6b8516d](https://github.com/Danube-Labs/javv-poc/commit/6b8516d7340fb080ebb03433a5b8b2167ceb0088))

## [0.2.5](https://github.com/Danube-Labs/javv-poc/compare/v0.2.4...v0.2.5) (2026-07-04)


### Features

* **m5a:** auth foundation — argon2id passwords + server-side sessions (slices 1–2) ([#127](https://github.com/Danube-Labs/javv-poc/issues/127)) ([dc0f79b](https://github.com/Danube-Labs/javv-poc/commit/dc0f79b5b312d30d65eabe016d0be37d3ea71afb))
* **m5a:** login/logout + lockout + bootstrap admin + capability RBAC (slices 3–4) ([#129](https://github.com/Danube-Labs/javv-poc/issues/129)) ([8334ceb](https://github.com/Danube-Labs/javv-poc/commit/8334ceb5593cbcfc7c9a0b59832be6fa0d50e190))
* **m5a:** tenant chokepoint + standing RBAC/IDOR suite + token admin + auth auditing (slices 5–6) ([#130](https://github.com/Danube-Labs/javv-poc/issues/130)) ([8a54f94](https://github.com/Danube-Labs/javv-poc/commit/8a54f94c689413f285a0f868e103ff58eea67f53))

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
