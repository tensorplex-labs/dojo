# Changelog

## [1.8.1](https://github.com/tensorplex-labs/dojo/compare/v1.8.0...v1.8.1) (2025-10-22)


### Bug Fixes

* return deregistered instead of empty string ([#114](https://github.com/tensorplex-labs/dojo/issues/114)) ([b49c4f6](https://github.com/tensorplex-labs/dojo/commit/b49c4f6f2ef3752da41fa3db0dada2cde3f737b8))
* return deregistered instead of empty string ([#114](https://github.com/tensorplex-labs/dojo/issues/114)) ([6f5174f](https://github.com/tensorplex-labs/dojo/commit/6f5174f6703c3df66ecde60cdb94687edb6a9e1d))

## [1.8.0](https://github.com/tensorplex-labs/dojo/compare/v1.7.0...v1.8.0) (2025-10-15)


### Features

* analytics batch upload ([#106](https://github.com/tensorplex-labs/dojo/issues/106)) ([b089e72](https://github.com/tensorplex-labs/dojo/commit/b089e722881d9802e918ce48f4fe1c7a958f1760))
* analytics batch upload ([#106](https://github.com/tensorplex-labs/dojo/issues/106)) ([0907df6](https://github.com/tensorplex-labs/dojo/commit/0907df6f53bb47238739d13f40549331774136a5))

## [1.7.0](https://github.com/tensorplex-labs/dojo/compare/v1.6.0...v1.7.0) (2025-10-06)


### Features

* post score analytics to task api ([#100](https://github.com/tensorplex-labs/dojo/issues/100)) ([89fb650](https://github.com/tensorplex-labs/dojo/commit/89fb6507d9e22c163d358896c0278f20523ac193))
* task analytics ([9c227d9](https://github.com/tensorplex-labs/dojo/commit/9c227d9f88b3ef086ced67edbf4e52542a82155c))
* task analytics ([9c227d9](https://github.com/tensorplex-labs/dojo/commit/9c227d9f88b3ef086ced67edbf4e52542a82155c))
* task analytics ([#97](https://github.com/tensorplex-labs/dojo/issues/97)) ([cbac097](https://github.com/tensorplex-labs/dojo/commit/cbac097ce070d37164f4eeb8e9c93990b36ea848))


### Bug Fixes

* classifying non-voters in analytics correctly ([#102](https://github.com/tensorplex-labs/dojo/issues/102)) ([067113e](https://github.com/tensorplex-labs/dojo/commit/067113ee5f24bb78741bffe3681308349add8de3))

## [1.6.0](https://github.com/tensorplex-labs/dojo/compare/v1.5.0...v1.6.0) (2025-10-02)


### Features

* reduce burn emission to 80% ([#95](https://github.com/tensorplex-labs/dojo/issues/95)) ([c04e36d](https://github.com/tensorplex-labs/dojo/commit/c04e36dc05378c4ad45b239f592276e9bf9441f6))


### Bug Fixes

* added more logging, returns 0 properly for trap task ([#91](https://github.com/tensorplex-labs/dojo/issues/91)) ([0db44e5](https://github.com/tensorplex-labs/dojo/commit/0db44e5a6e5957aeed25bc3c969363a42e079849))
* added more logging, returns 0 properly for trap task ([#91](https://github.com/tensorplex-labs/dojo/issues/91)) ([dd12892](https://github.com/tensorplex-labs/dojo/commit/dd128926ad329256e2189fe34e7df4a641a0bc47))
* trap generators do not get penalize, now distributes vote penalties across non-voters ([#94](https://github.com/tensorplex-labs/dojo/issues/94)) ([5dc9d0e](https://github.com/tensorplex-labs/dojo/commit/5dc9d0e8bede09dbfddddd5c0aeaabb3fd7ed41d))

## [1.5.0](https://github.com/tensorplex-labs/dojo/compare/v1.4.0...v1.5.0) (2025-10-01)


### Features

* burn weights if there is no weights to be set ([#87](https://github.com/tensorplex-labs/dojo/issues/87)) ([f3dc6d5](https://github.com/tensorplex-labs/dojo/commit/f3dc6d59942b4e063e20aa45412601feb8dbf359))
* burn weights if there is no weights to be set ([#87](https://github.com/tensorplex-labs/dojo/issues/87)) ([6c59683](https://github.com/tensorplex-labs/dojo/commit/6c59683ed53c739f1e9edb1859847aa18ba6798f))


### Bug Fixes

* divide into percentage for burn weight ([#89](https://github.com/tensorplex-labs/dojo/issues/89)) ([df92661](https://github.com/tensorplex-labs/dojo/commit/df92661579f1bd28730551975cd4687d08ecdcf9))

## [1.4.0](https://github.com/tensorplex-labs/dojo/compare/v1.3.1...v1.4.0) (2025-10-01)


### Features

* miners penalisation for not voting ([fca6dd0](https://github.com/tensorplex-labs/dojo/commit/fca6dd079a13fc51476221c993e85373ecf639e7))
* penalising miners ([#83](https://github.com/tensorplex-labs/dojo/issues/83)) ([dfa760b](https://github.com/tensorplex-labs/dojo/commit/dfa760b082846a4e3497284ee4b5dec3ecb450a1))


### Bug Fixes

* assignee bug where trap hotkeys are not getting the right prompts ([#84](https://github.com/tensorplex-labs/dojo/issues/84)) ([b70cb7b](https://github.com/tensorplex-labs/dojo/commit/b70cb7b5044f4d03a34e9fe0bcf0a9376dcbc187))

## [1.3.1](https://github.com/tensorplex-labs/dojo/compare/v1.3.0...v1.3.1) (2025-09-30)


### Bug Fixes

* trap tasks pop issue and reduce vali duels ([#81](https://github.com/tensorplex-labs/dojo/issues/81)) ([75a7d56](https://github.com/tensorplex-labs/dojo/commit/75a7d562181d08cb3f0d47b3c8efc0f264a37a0a))

## [1.3.0](https://github.com/tensorplex-labs/dojo/compare/v1.2.1...v1.3.0) (2025-09-29)


### Features

* updated scores retaining logic and weights setting intervals ([#76](https://github.com/tensorplex-labs/dojo/issues/76)) ([1d614f3](https://github.com/tensorplex-labs/dojo/commit/1d614f39f10894764cd41ac8b55a2928d86a0de2))


## [1.2.1](https://github.com/tensorplex-labs/dojo/compare/v1.2.0...v1.2.1) (2025-09-25)


### Bug Fixes

* fixing negative weights issues by clamping it to 0 instead ([#69](https://github.com/tensorplex-labs/dojo/issues/69)) ([ec85cf4](https://github.com/tensorplex-labs/dojo/commit/ec85cf4307518e79b41d11ab84d8991dab19bf12))

## [1.2.0](https://github.com/tensorplex-labs/dojo/compare/v1.1.2...v1.2.0) (2025-09-24)


### Features

* incr. task and scoring interval ([d91838e](https://github.com/tensorplex-labs/dojo/commit/d91838e791ecc96d16d49afd93189a3e4e86288f))

## [1.1.2](https://github.com/tensorplex-labs/dojo/compare/v1.1.1...v1.1.2) (2025-09-24)


### Bug Fixes

* typo in env example file ([c890e1c](https://github.com/tensorplex-labs/dojo/commit/c890e1c51392345b26d20eb152295944f3a608eb))

## [1.1.1](https://github.com/tensorplex-labs/dojo/compare/v1.1.0...v1.1.1) (2025-09-24)


### Bug Fixes

* show preburn weights and map active miners by hotkeys instead of axons ([aca40f4](https://github.com/tensorplex-labs/dojo/commit/aca40f44f2b8aef8845078f48a5468755ca4e073))
* show preburn weights and map active miners by hotkeys instead of axons ([aca40f4](https://github.com/tensorplex-labs/dojo/commit/aca40f44f2b8aef8845078f48a5468755ca4e073))

## [1.1.0](https://github.com/tensorplex-labs/dojo/compare/v1.0.3...v1.1.0) (2025-09-24)


### Features

* set burn to 95% ([ce53694](https://github.com/tensorplex-labs/dojo/commit/ce53694bb050423909cce7d34859d0c2df1f7832))

## [1.0.3](https://github.com/tensorplex-labs/dojo-v2/compare/v1.0.2...v1.0.3) (2025-09-20)


### Bug Fixes

* scoring bug and some docs update for clarity ([28d6fc7](https://github.com/tensorplex-labs/dojo-v2/commit/28d6fc723a6f2bd4c1c948099ca2ccd9871f0112))
* scoring bug and some docs update for clarity ([28d6fc7](https://github.com/tensorplex-labs/dojo-v2/commit/28d6fc723a6f2bd4c1c948099ca2ccd9871f0112))

## [1.0.2](https://github.com/tensorplex-labs/dojo-v2/compare/v1.0.1...v1.0.2) (2025-09-18)


### Bug Fixes

* add modifiable config for task expiry ([ae89801](https://github.com/tensorplex-labs/dojo-v2/commit/ae898011789fcfaa9a87ecfd912aa33029d8689b))
* add modifiable config for task expiry ([ae89801](https://github.com/tensorplex-labs/dojo-v2/commit/ae898011789fcfaa9a87ecfd912aa33029d8689b))
* fix the typo of specifying the round interval ([72e4c7d](https://github.com/tensorplex-labs/dojo-v2/commit/72e4c7d86cb89f411e85bd8c680a2c7061245ee4))
* further shorten task expiry to 10mins ([f2701ff](https://github.com/tensorplex-labs/dojo-v2/commit/f2701ff615926feea5c3d570649dc15130172ee4))
* hotfix for enum fix in task update api and changed scoring interval for dev ([584acc5](https://github.com/tensorplex-labs/dojo-v2/commit/584acc5ecb818485cdb10431f65841490f2c92b5))
* testnet release ([2cf69c6](https://github.com/tensorplex-labs/dojo-v2/commit/2cf69c65b2156e4eb77c3d2d15a748589733d9d1))
* testnet release ([2cf69c6](https://github.com/tensorplex-labs/dojo-v2/commit/2cf69c65b2156e4eb77c3d2d15a748589733d9d1))

## [1.0.1](https://github.com/tensorplex-labs/dojo-v2/compare/v1.0.0...v1.0.1) (2025-09-18)


### Bug Fixes

* fixed synthetic gen issues ([1c226b4](https://github.com/tensorplex-labs/dojo-v2/commit/1c226b4d64808905497ff1b32d9adf3e2a584851))
* fixed synthetic gen issues ([1c226b4](https://github.com/tensorplex-labs/dojo-v2/commit/1c226b4d64808905497ff1b32d9adf3e2a584851))
* fixed synthetic-gen issues ([1413fdc](https://github.com/tensorplex-labs/dojo-v2/commit/1413fdc09e85151d20895d57e2a4d58e2984fb79))
* fixed typing in syntheticgen interface ([b6aa0eb](https://github.com/tensorplex-labs/dojo-v2/commit/b6aa0eb4e835a0acfe9b4d68e3b5cf1182b73f3b))
* pop qa questions response endpoint integration ([39f3333](https://github.com/tensorplex-labs/dojo-v2/commit/39f33334ace8b4707d66f0e840a930f96646ced9))
* synthetic gen api popping mechanism ([f63c0af](https://github.com/tensorplex-labs/dojo-v2/commit/f63c0aff00945881b1f372029383af86bbb839b6))
* synthetic gen api popping mechanism ([f63c0af](https://github.com/tensorplex-labs/dojo-v2/commit/f63c0aff00945881b1f372029383af86bbb839b6))
* synthetic gen popping due to new types ([6c67551](https://github.com/tensorplex-labs/dojo-v2/commit/6c675519f10a3fc7dfb6d725f5476d6af5587cb4))
* synthetic gen popping due to new types ([6c67551](https://github.com/tensorplex-labs/dojo-v2/commit/6c675519f10a3fc7dfb6d725f5476d6af5587cb4))

## 1.0.0 (2025-09-17)


### Features

* dojo v2 ([f5fbe8d](https://github.com/tensorplex-labs/dojo-v2/commit/f5fbe8d32f132c398ad414a462040239bfa4b425))
