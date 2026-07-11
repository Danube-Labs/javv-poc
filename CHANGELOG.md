# Changelog

## [0.3.9](https://github.com/Danube-Labs/javv-poc/compare/v0.3.8...v0.3.9) (2026-07-11)


### Features

* **ui:** chip language A — derived hues, severity escalation, one depth treatment ([#350](https://github.com/Danube-Labs/javv-poc/issues/350)) ([229a728](https://github.com/Danube-Labs/javv-poc/commit/229a728728fdb733ce81cac128da9ad1f91b444b))
* **ui:** grid ergonomics — column drag-reorder on findings + images, cursor contract, first-seen column ([#348](https://github.com/Danube-Labs/javv-poc/issues/348)) ([a24e768](https://github.com/Danube-Labs/javv-poc/commit/a24e768c55d919d1f25714050f294e56ef494f09))


### Bug Fixes

* **api:** cap hourly trend buckets at a month of span ([#346](https://github.com/Danube-Labs/javv-poc/issues/346)) ([a562b1e](https://github.com/Danube-Labs/javv-poc/commit/a562b1e49d93b43b403bd324368a030e1e9b20d0)), closes [#343](https://github.com/Danube-Labs/javv-poc/issues/343)

## [0.3.8](https://github.com/Danube-Labs/javv-poc/compare/v0.3.7...v0.3.8) (2026-07-11)


### Features

* **api:** severity split on the findings trend ([#333](https://github.com/Danube-Labs/javv-poc/issues/333)) ([77801c6](https://github.com/Danube-Labs/javv-poc/commit/77801c6a0788e265a5bf9bc854d638c5554e3c48))
* **ui:** m9c slice 1 — the overview dashboard ([#332](https://github.com/Danube-Labs/javv-poc/issues/332)) ([406dedf](https://github.com/Danube-Labs/javv-poc/commit/406dedf866da65acf720da33ffcd6d9c4892cc14)), closes [#37](https://github.com/Danube-Labs/javv-poc/issues/37)
* **ui:** M9c slice 2 — the all-clusters fleet view ([#338](https://github.com/Danube-Labs/javv-poc/issues/338)) ([bcf7485](https://github.com/Danube-Labs/javv-poc/commit/bcf748510f02c41f4e019482cdfd5f15fe36f101))
* **ui:** M9c slice 3 — running images + image detail on the committed inventory ([#339](https://github.com/Danube-Labs/javv-poc/issues/339)) ([4312607](https://github.com/Danube-Labs/javv-poc/commit/431260720b3ba48ed4587d91ad9e99fd840b4909))
* **ui:** overview 1b — severity lens, signal band, at-rest affordances ([#334](https://github.com/Danube-Labs/javv-poc/issues/334)) ([486e2ae](https://github.com/Danube-Labs/javv-poc/commit/486e2aef008e457ccf103f6137bee142773339c0)), closes [#37](https://github.com/Danube-Labs/javv-poc/issues/37)
* **ui:** scan-ingest lens above the findings + images tables ([#340](https://github.com/Danube-Labs/javv-poc/issues/340)) ([95eaa2f](https://github.com/Danube-Labs/javv-poc/commit/95eaa2fdc75ca96300574c6344df96824b273b7a)), closes [#37](https://github.com/Danube-Labs/javv-poc/issues/37)


### Bug Fixes

* **ui:** audit-343 wave — honest errors, restorable time range, semantics everywhere ([#344](https://github.com/Danube-Labs/javv-poc/issues/344)) ([19d3dfb](https://github.com/Danube-Labs/javv-poc/commit/19d3dfb7ec5cbc2d98845d82bbb2c96986bb52f3)), closes [#343](https://github.com/Danube-Labs/javv-poc/issues/343)
* **ui:** freshness banner — urgency treatment, 24h times, durations, 10-min poll ([#330](https://github.com/Danube-Labs/javv-poc/issues/330)) ([7e1c991](https://github.com/Danube-Labs/javv-poc/commit/7e1c9910a2ef0c0e293eeb091211d62ef269756a))
* **ui:** overview + findings polish — cursor, donut links, palette, note, column diet ([#335](https://github.com/Danube-Labs/javv-poc/issues/335)) ([ae706ce](https://github.com/Danube-Labs/javv-poc/commit/ae706ce686ef16a15208ab8a25a5023659be697f))
* **ui:** system-default cursor truly global — universal rule + ratchet ([#337](https://github.com/Danube-Labs/javv-poc/issues/337)) ([023f19b](https://github.com/Danube-Labs/javv-poc/commit/023f19b7c7f4336820cc9a19e7463a9bc8f23b32)), closes [#37](https://github.com/Danube-Labs/javv-poc/issues/37)

## [0.3.7](https://github.com/Danube-Labs/javv-poc/compare/v0.3.6...v0.3.7) (2026-07-10)


### Features

* **ui:** collapsible icon-rail sidebar (226px ↔ 64px, Nuxt UI grammar) ([#320](https://github.com/Danube-Labs/javv-poc/issues/320)) ([cff81a3](https://github.com/Danube-Labs/javv-poc/commit/cff81a384d9250f40f89c7010566b822abdbe2a3)), closes [#319](https://github.com/Danube-Labs/javv-poc/issues/319)
* **ui:** motion layer — open/close transitions baked into the kit ([#323](https://github.com/Danube-Labs/javv-poc/issues/323)) ([fcd1552](https://github.com/Danube-Labs/javv-poc/commit/fcd155226a99ff61b7764d8f191377d7f1d90cc6))
* **ui:** toast notifications — the app-wide confirmation channel ([#324](https://github.com/Danube-Labs/javv-poc/issues/324)) ([8bfed97](https://github.com/Danube-Labs/javv-poc/commit/8bfed97921b1794a12379d152b36129ddbf82ad9)), closes [#319](https://github.com/Danube-Labs/javv-poc/issues/319)


### Bug Fixes

* **audit:** activity feed updates without a page reload ([#321](https://github.com/Danube-Labs/javv-poc/issues/321)) ([ee51640](https://github.com/Danube-Labs/javv-poc/commit/ee51640092123e72422705c0a0c136a78bb6bb78))

## [0.3.6](https://github.com/Danube-Labs/javv-poc/compare/v0.3.5...v0.3.6) (2026-07-10)


### Features

* **dx:** agent design contract, style ratchet, /visual-test + /qa commands ([#285](https://github.com/Danube-Labs/javv-poc/issues/285)) ([f8b2cfb](https://github.com/Danube-Labs/javv-poc/commit/f8b2cfbd0bc4fab9d01fdc5d104a9dbf1990dbec)), closes [#284](https://github.com/Danube-Labs/javv-poc/issues/284)
* **m9a:** app shell, login + must_change, banners, global time picker (slice 3) ([#289](https://github.com/Danube-Labs/javv-poc/issues/289)) ([8c915ad](https://github.com/Danube-Labs/javv-poc/commit/8c915ad35ce9b3473ad2b45f6bdb12af71766c1c))
* **m9a:** frontend scaffold, design tokens, style gates, fe logger (slice 1) ([#287](https://github.com/Danube-Labs/javv-poc/issues/287)) ([59f6428](https://github.com/Danube-Labs/javv-poc/commit/59f642823ccd6c66c28fa8a0688e306e658fd765))
* **m9a:** reusable filter module — one fields config drives rail + bar (slice 4) ([#290](https://github.com/Danube-Labs/javv-poc/issues/290)) ([bfb3a95](https://github.com/Danube-Labs/javv-poc/commit/bfb3a9501e18d2f40b2436e106eeafb2ef92104a))
* **m9a:** typed api client + i4/i7 contract gate (slice 2) ([#288](https://github.com/Danube-Labs/javv-poc/issues/288)) ([55e70ac](https://github.com/Danube-Labs/javv-poc/commit/55e70ac73aff21d9a9b2de80f6e927c0b662bb4c)), closes [#35](https://github.com/Danube-Labs/javv-poc/issues/35)
* **m9b:** bulk triage, export dialog, metadata pack — slice 4 (bolt wrap) ([#309](https://github.com/Danube-Labs/javv-poc/issues/309)) ([e115d18](https://github.com/Danube-Labs/javv-poc/commit/e115d18d3b730d6b2ba8f4e0fc80b4773abab601))
* **m9b:** finding detail screen — per-scanner evidence, images affected, cve-click navigation (slice 2) ([#304](https://github.com/Danube-Labs/javv-poc/issues/304)) ([c4eb6f0](https://github.com/Danube-Labs/javv-poc/commit/c4eb6f0fc5a3ce1cf0b2f55f12c6d17b8dec6ea8))
* **m9b:** shared chip set + lazy findings grid (slice 1) ([#292](https://github.com/Danube-Labs/javv-poc/issues/292)) ([ed40437](https://github.com/Danube-Labs/javv-poc/commit/ed404379c39d109aebc9a528e067ecefb9f94ed2))
* **m9b:** triage panel — 6-state vex, risk-accept dialog, decisions card (slice 3) ([#305](https://github.com/Danube-Labs/javv-poc/issues/305)) ([0af963f](https://github.com/Danube-Labs/javv-poc/commit/0af963f773d332777e27b708e675b9fdc78f0a4b))
* prototype-fidelity time picker + columns menu on the findings grid ([#297](https://github.com/Danube-Labs/javv-poc/issues/297)) ([aeb92ec](https://github.com/Danube-Labs/javv-poc/commit/aeb92ec596582391ad646e30a021f41659c7f767)), closes [#296](https://github.com/Danube-Labs/javv-poc/issues/296)
* switch ui font to hanken grotesk (operator a/b ruling) ([#295](https://github.com/Danube-Labs/javv-poc/issues/295)) ([eb89282](https://github.com/Danube-Labs/javv-poc/commit/eb89282dc905fefa97f439c78b9ad63b9600f138))
* **ui:** interaction feedback + spacing rhythm + surface elevation pass ([#307](https://github.com/Danube-Labs/javv-poc/issues/307)) ([9b81c83](https://github.com/Danube-Labs/javv-poc/commit/9b81c830ebaa9beabacd20b4ed25979a93c83340))


### Bug Fixes

* **m9b:** as_of reader rejects q explicitly; parity guard against ignored filters ([#310](https://github.com/Danube-Labs/javv-poc/issues/310)) ([f6c5936](https://github.com/Danube-Labs/javv-poc/commit/f6c5936ba8b76af3e3bd35d7f5803d7bd511d86c))
* **ui:** visible hover feedback on every control + unclipped segmented bars ([#314](https://github.com/Danube-Labs/javv-poc/issues/314)) ([662c00c](https://github.com/Danube-Labs/javv-poc/commit/662c00c528934635895abf2c6c509aa8b53757e7))
* wcag aa contrast for hint text, dark-chrome labels and teal text ([#294](https://github.com/Danube-Labs/javv-poc/issues/294)) ([5aee72b](https://github.com/Danube-Labs/javv-poc/commit/5aee72beabbba44bdd095d340dcf671b84256f39))

## [0.3.5](https://github.com/Danube-Labs/javv-poc/compare/v0.3.4...v0.3.5) (2026-07-08)


### Features

* **274:** full-word canonical severity — severity_canonical query key + sla fix (slice 1) ([#277](https://github.com/Danube-Labs/javv-poc/issues/277)) ([5a74dc8](https://github.com/Danube-Labs/javv-poc/commit/5a74dc85074d1ca2f9293a5dee677c1bcd7030a6)), closes [#274](https://github.com/Danube-Labs/javv-poc/issues/274)
* **274:** scanner full-word severities + count-column shim, smoke vocabulary pin (slice 2) ([#278](https://github.com/Danube-Labs/javv-poc/issues/278)) ([7c8ffb8](https://github.com/Danube-Labs/javv-poc/commit/7c8ffb8bd2f252267343f024e4e4dccbdd5c7bb9)), closes [#274](https://github.com/Danube-Labs/javv-poc/issues/274)
* **m8e:** system-views store + create/list — the saved-views foundation (slice 1) ([#273](https://github.com/Danube-Labs/javv-poc/issues/273)) ([050b23a](https://github.com/Danube-Labs/javv-poc/commit/050b23ade6afd2e4aa6650eb157190528978716a)), closes [#242](https://github.com/Danube-Labs/javv-poc/issues/242)
* **m8e:** views mutations — owner-or-admin, cas, and the deep-link round-trip (slice 2) ([#276](https://github.com/Danube-Labs/javv-poc/issues/276)) ([b7e80da](https://github.com/Danube-Labs/javv-poc/commit/b7e80dacf39b53e934f585dc42ba575fd7305198)), closes [#242](https://github.com/Danube-Labs/javv-poc/issues/242)


### Bug Fixes

* **trends:** absolute window bounds — kill the createWeight now-datemath ci flake ([#279](https://github.com/Danube-Labs/javv-poc/issues/279)) ([fd81951](https://github.com/Danube-Labs/javv-poc/commit/fd81951dd9ccbd74fea691c7e641e9443576455e))

## [0.3.4](https://github.com/Danube-Labs/javv-poc/compare/v0.3.3...v0.3.4) (2026-07-08)


### Features

* **m8c:** audit read + catalog-first scanner provenance (slice 1) ([#267](https://github.com/Danube-Labs/javv-poc/issues/267)) ([b5d322b](https://github.com/Danube-Labs/javv-poc/commit/b5d322b8fe53e745c9c675af385a50a9df459c1e)), closes [#240](https://github.com/Danube-Labs/javv-poc/issues/240)
* **m8c:** running-images read + cluster registry — the m9-prep reads close (slice 2) ([#269](https://github.com/Danube-Labs/javv-poc/issues/269)) ([#270](https://github.com/Danube-Labs/javv-poc/issues/270)) ([73ef41b](https://github.com/Danube-Labs/javv-poc/commit/73ef41b7deef44c23ce88a5bddc42de44609f8be)), closes [#240](https://github.com/Danube-Labs/javv-poc/issues/240)
* **m8d:** ptype through every read surface — filter, facets, groups, as-of-t (slice 2) ([#272](https://github.com/Danube-Labs/javv-poc/issues/272)) ([dea5136](https://github.com/Danube-Labs/javv-poc/commit/dea5136bb51d47527c1490142618cdafe635ff30)), closes [#241](https://github.com/Danube-Labs/javv-poc/issues/241)
* **m8d:** ptype through the write path — envelope v4 with a v3 acceptance window (slice 1) ([#271](https://github.com/Danube-Labs/javv-poc/issues/271)) ([9ee1fea](https://github.com/Danube-Labs/javv-poc/commit/9ee1fea89287d5152b423dbe92e3977bc5505b40)), closes [#241](https://github.com/Danube-Labs/javv-poc/issues/241)

## [0.3.3](https://github.com/Danube-Labs/javv-poc/compare/v0.3.2...v0.3.3) (2026-07-07)


### Features

* **m8a:** inventory commit manifest + cycle-end certification (slice 2) ([#256](https://github.com/Danube-Labs/javv-poc/issues/256)) ([1ace495](https://github.com/Danube-Labs/javv-poc/commit/1ace495a1867006a5f38b253d5beecf60bf58292)), closes [#33](https://github.com/Danube-Labs/javv-poc/issues/33)
* **m8a:** per-scan occurrence snapshots appended in the d39 spine (slice 1) ([#254](https://github.com/Danube-Labs/javv-poc/issues/254)) ([c2b16df](https://github.com/Danube-Labs/javv-poc/commit/c2b16dfc1ceba6eeba6373198a711966defb7781)), closes [#33](https://github.com/Danube-Labs/javv-poc/issues/33)
* **m8a:** rebuild-state scanner-presence arm + exact self-heal floor (slice 3) ([#258](https://github.com/Danube-Labs/javv-poc/issues/258)) ([c27f36f](https://github.com/Danube-Labs/javv-poc/commit/c27f36f6bd70619e14db24cebd8badd6d7e1b731))
* **m8b:** audit replay + decisions-active-at-t — the human dimension (slice 2) ([#264](https://github.com/Danube-Labs/javv-poc/issues/264)) ([2a091ee](https://github.com/Danube-Labs/javv-poc/commit/2a091eea9a75400035fac6caffe510e126d327a3))
* **m8b:** r-catalog point-in-time primitives (slice 1) ([#263](https://github.com/Danube-Labs/javv-poc/issues/263)) ([36670d7](https://github.com/Danube-Labs/javv-poc/commit/36670d742f38e95af3cebbefc056605463d4d7ab)), closes [#34](https://github.com/Danube-Labs/javv-poc/issues/34)
* **m8b:** the as-of-t reader — findings page/facets/groups reconstructed (slice 3) ([#265](https://github.com/Danube-Labs/javv-poc/issues/265)) ([29f735a](https://github.com/Danube-Labs/javv-poc/commit/29f735a94e5afbc789c11e6150bc0c0c95e54d6f)), closes [#34](https://github.com/Danube-Labs/javv-poc/issues/34)
* **m8b:** trends + contributors at t, reader registration, export unpark (slice 4) ([#266](https://github.com/Danube-Labs/javv-poc/issues/266)) ([da961e8](https://github.com/Danube-Labs/javv-poc/commit/da961e88b651ce02e8a7a98c50b6c66f10e9ad19))


### Bug Fixes

* **ci:** allow fs.read=.. in the scanner-images bake — buildx runner drift enforces entitlements ([#260](https://github.com/Danube-Labs/javv-poc/issues/260)) ([7e2a0ec](https://github.com/Danube-Labs/javv-poc/commit/7e2a0ec53caca24e84b0cfb6bafba3731128a98f))

## [0.3.2](https://github.com/Danube-Labs/javv-poc/compare/v0.3.1...v0.3.2) (2026-07-07)


### Features

* **m7:** bulk_triage report kind — capability-gated, frozen at enqueue (slice 5) ([#252](https://github.com/Danube-Labs/javv-poc/issues/252)) ([6c4c442](https://github.com/Danube-Labs/javv-poc/commit/6c4c44227cf71d5bf0f41c7eeb7d79e8e562c907)), closes [#32](https://github.com/Danube-Labs/javv-poc/issues/32)
* **m7:** drain worker, chunked results, signed download, notifications bell (slice 3) ([#248](https://github.com/Danube-Labs/javv-poc/issues/248)) ([83ca734](https://github.com/Danube-Labs/javv-poc/commit/83ca73491be849d5528e41472c8224b4d13254f0)), closes [#32](https://github.com/Danube-Labs/javv-poc/issues/32)
* **m7:** occ claim + fenced lease for the report queue (slice 2) ([#246](https://github.com/Danube-Labs/javv-poc/issues/246)) ([8a7d71b](https://github.com/Danube-Labs/javv-poc/commit/8a7d71b36b9f0ce82fcf09a17713eb4c3663bf28)), closes [#32](https://github.com/Danube-Labs/javv-poc/issues/32)
* **m7:** ttl + orphan sweep for the report queue (slice 4) ([#251](https://github.com/Danube-Labs/javv-poc/issues/251)) ([b7b99d7](https://github.com/Danube-Labs/javv-poc/commit/b7b99d7b53b1fddef3f6249fd28b928765be5b93)), closes [#32](https://github.com/Danube-Labs/javv-poc/issues/32)


### Bug Fixes

* **ci:** serialize the store-exclusive admin demote race — it 401'd concurrent tests ([#250](https://github.com/Danube-Labs/javv-poc/issues/250)) ([49ce86a](https://github.com/Danube-Labs/javv-poc/commit/49ce86ae255fca9b0998b9aacb2815cf4c306bbf)), closes [#245](https://github.com/Danube-Labs/javv-poc/issues/245)

## [0.3.1](https://github.com/Danube-Labs/javv-poc/compare/v0.3.0...v0.3.1) (2026-07-07)


### Features

* expand /metrics — request histogram, os health, cas churn, limits, auth (audit [#220](https://github.com/Danube-Labs/javv-poc/issues/220)) ([#229](https://github.com/Danube-Labs/javv-poc/issues/229)) ([101c009](https://github.com/Danube-Labs/javv-poc/commit/101c009848c076397a82ea6d1b560f787c19b04a)), closes [#66](https://github.com/Danube-Labs/javv-poc/issues/66)
* **m6:** scanner-freshness read — get /api/v1/scanners/freshness (audit d-1, [#218](https://github.com/Danube-Labs/javv-poc/issues/218)) ([#227](https://github.com/Danube-Labs/javv-poc/issues/227)) ([1aab7a1](https://github.com/Danube-Labs/javv-poc/commit/1aab7a1476f71f7b4958962c33887a4dc991366c)), closes [#35](https://github.com/Danube-Labs/javv-poc/issues/35)
* **m7:** scheduled-export queue foundation — indexes + enqueue endpoint (slice 1, [#32](https://github.com/Danube-Labs/javv-poc/issues/32)) ([#213](https://github.com/Danube-Labs/javv-poc/issues/213)) ([a5d714d](https://github.com/Danube-Labs/javv-poc/commit/a5d714d0d010a8b0d4cdd5fca7e4368640b8dffb))
* validate settings at boot — borked config crash-loops readably (audit [#219](https://github.com/Danube-Labs/javv-poc/issues/219)) ([#228](https://github.com/Danube-Labs/javv-poc/issues/228)) ([f0a44e4](https://github.com/Danube-Labs/javv-poc/commit/f0a44e4a28cab6fb3b237d7ca723c16334fc6816)), closes [#66](https://github.com/Danube-Labs/javv-poc/issues/66)

## [0.3.0](https://github.com/Danube-Labs/javv-poc/compare/v0.2.16...v0.3.0) (2026-07-06)


### Features

* **m5c:** warn when reproject drains a conflict storm (audit [#186](https://github.com/Danube-Labs/javv-poc/issues/186) nicety) ([#201](https://github.com/Danube-Labs/javv-poc/issues/201)) ([ae0c17e](https://github.com/Danube-Labs/javv-poc/commit/ae0c17e1aadbc1b80f18bdabf22dd9f481a7057e))


### Bug Fixes

* **m5c:** journal-first audit completeness on new write paths + last-admin race (audit [#188](https://github.com/Danube-Labs/javv-poc/issues/188)) ([#204](https://github.com/Danube-Labs/javv-poc/issues/204)) ([cba3987](https://github.com/Danube-Labs/javv-poc/commit/cba3987cc4027760341bd6baccc98df604e37ebd))
* **m5c:** reproject_cve guarded RMW — drain conflicts, re-check ownership (audit [#186](https://github.com/Danube-Labs/javv-poc/issues/186)) ([#197](https://github.com/Danube-Labs/javv-poc/issues/197)) ([87bf402](https://github.com/Danube-Labs/javv-poc/commit/87bf4028f7d378a28845e0ec60dd377e16c60bc3))
* **m5d:** exact paged-composite group clock, no sibling truncation (audit [#187](https://github.com/Danube-Labs/javv-poc/issues/187)) ([#200](https://github.com/Danube-Labs/javv-poc/issues/200)) ([dc1c728](https://github.com/Danube-Labs/javv-poc/commit/dc1c728577b924d433c55622e9199c04b13fb3f6))
* **m6:** bound export/read-path DoS — bulk sync + export/PIT caps (audit [#189](https://github.com/Danube-Labs/javv-poc/issues/189)) ([#206](https://github.com/Danube-Labs/javv-poc/issues/206)) ([7ac2ff1](https://github.com/Danube-Labs/javv-poc/commit/7ac2ff1e73cc379c9ed4fab50f56d6fdfb40e722))
* **m6:** contributors — count decision rows + page handling rows (audit [#190](https://github.com/Danube-Labs/javv-poc/issues/190)) ([#207](https://github.com/Danube-Labs/javv-poc/issues/207)) ([582125f](https://github.com/Danube-Labs/javv-poc/commit/582125fc3a1f845b603b054b2e861867c93aac4f))
* **m6:** hardening & hygiene batch — reserved usernames, redaction, purl, docs (audit [#192](https://github.com/Danube-Labs/javv-poc/issues/192)) ([#210](https://github.com/Danube-Labs/javv-poc/issues/210)) ([048687f](https://github.com/Danube-Labs/javv-poc/commit/048687f4480ed713d9b3664c03f5bd9f748068e2))
* **m6:** read-path robustness — cursor errors 4xx + drop read-side refresh (audit [#191](https://github.com/Danube-Labs/javv-poc/issues/191)) ([#209](https://github.com/Danube-Labs/javv-poc/issues/209)) ([1cfe3ee](https://github.com/Danube-Labs/javv-poc/commit/1cfe3ee5fba3fddddd424160449fe01ee8223e89))


### Miscellaneous Chores

* cut the 0.3.0 minor release (audit wave) ([#211](https://github.com/Danube-Labs/javv-poc/issues/211)) ([c8d3251](https://github.com/Danube-Labs/javv-poc/commit/c8d325141d7244313befd13190c6d835c5f3deaa))

## [0.2.16](https://github.com/Danube-Labs/javv-poc/compare/v0.2.15...v0.2.16) (2026-07-06)


### Bug Fixes

* **m5c/m6:** validate triage + decision vocabularies (audit [#185](https://github.com/Danube-Labs/javv-poc/issues/185)) ([#195](https://github.com/Danube-Labs/javv-poc/issues/195)) ([b371923](https://github.com/Danube-Labs/javv-poc/commit/b3719238311cc34bdd067424be287b29f1408b17))

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
